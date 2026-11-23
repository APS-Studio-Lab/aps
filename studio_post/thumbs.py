"""Thumbnails: the presenter's strongest real expressions over an episode scene, in the channel's layout.

python -m studio_post.thumbs path/to/job.yaml --work work/<job>

job.yaml:
  thumbnail:
    tag: "..."                 # small gold tag
    lines: ["...", "..."]      # 2-5 words in total; the second line is the gold accent
    scenes: [thumbs/scene_1, thumbs/scene_2, thumbs/scene_3]   # any image extension; made with docs/prompts/thumbnails.md
    at_s: [ ... ]              # optional: force these moments for the presenter instead of auto-picking

The presenter always comes from a real frame of the footage (never generated). Faces are picked automatically:
sharp, facing the camera, clearly expressive; Gemini ranks the shortlist when a key is available.
Outputs 3 finished 1280x720 thumbnails plus a contact sheet of the shortlist, for the human gate.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import yaml

from . import brandkit
from .analyze import MODEL
from .keyer import Keyer, despill
from .util import FONTS, REPO, StageError, ffprobe, fill, Browser

W, H = 640, 360


def _decode(video: Path, fps: float, w: int, h: int, start: float | None = None, frames: int | None = None):
    info = ffprobe(video)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    hdr = vs.get("color_transfer") in ("arib-std-b67", "smpte2084")
    vf = f"fps={fps},"
    if hdr:
        vf += "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
    vf += f"scale={w}:{h}"
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{start:.3f}"] if start is not None else []) + ["-i", str(video)]
    cmd += (["-frames:v", str(frames)] if frames else []) + ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.wait()


def _green(f: np.ndarray) -> float:
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 0] > 35) & (hsv[..., 0] < 90) & (hsv[..., 1] > 60) & (hsv[..., 2] > 40)).mean())


def _quiet_times(video: Path, step_s: float) -> np.ndarray:
    """Per sample time: True when the voice is silent (between sentences), so the mouth is at rest."""
    from .ingest import _pcm
    rate = 16000
    a = _pcm(video, rate)
    hop = int(rate * step_s)
    n = len(a) // hop
    win = int(rate * 0.12)
    db = []
    for i in range(n):
        c = i * hop
        seg = a[max(0, c - win):c + win]
        db.append(20 * np.log10(np.sqrt(np.mean(seg.astype(np.float64) ** 2)) + 1e-9))
    db = np.array(db)
    floor = np.percentile(db, 10)
    return db < floor + 9  # within ~9 dB of the room tone


def shortlist(video: Path, step_s: float = 0.25, keep: int = 24, spacing_s: float = 4.0):
    """Sharp, frontal, green-screen frames with a face, taken only in pauses (mouth at rest); spread out."""
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (W, H), 0.7)
    quiet = _quiet_times(video, step_s)
    cands, samples = [], []
    for i, f in enumerate(_decode(video, 1 / step_s, W, H)):
        t = i * step_s
        if _green(f) < 0.25:
            continue
        if len(samples) < 40 and i % 40 == 0:
            samples.append(f.copy())
        at_rest = bool(i < len(quiet) and quiet[i])
        _, faces = det.detect(f)
        if faces is None or not len(faces):
            continue
        fc = max(faces, key=lambda r: r[2] * r[3])
        x, y, w, h = fc[:4]
        (rex, rey), (lex, ley), (nx, ny) = fc[4:6], fc[6:8], fc[8:10]
        eye_d = max(abs(lex - rex), 1)
        eye_y, mouth_y = (rey + ley) / 2, (fc[11] + fc[13]) / 2
        pitch = (ny - eye_y) / max(1.0, mouth_y - eye_y)  # same measure as the edit: >0.64 means looking down
        if pitch > 0.62 or fc[14] < 0.85:
            continue
        frontal = 1 - min(1, abs((nx - (rex + lex) / 2) / eye_d) * 1.6) - min(1, abs(ley - rey) / eye_d)
        crop = cv2.cvtColor(f[int(max(y, 0)):int(y + h), int(max(x, 0)):int(x + w)], cv2.COLOR_BGR2GRAY)
        if crop.size == 0:
            continue
        sharp = cv2.Laplacian(crop, cv2.CV_64F).var()
        cands.append({"t": t, "rest": at_rest, "box": [float(v) for v in (x, y, w, h)], "score": float(fc[14]),
                      "frontal": float(frontal), "sharp": float(sharp), "thumb": f})
    if not cands:
        raise StageError("no usable face frames on green screen found for the thumbnail")
    if len(samples) < 3:
        samples = [c["thumb"] for c in cands[:: max(1, len(cands) // 12)]]
    sh = np.array([c["sharp"] for c in cands]); sh = sh / (np.percentile(sh, 90) + 1e-6)
    for c, s in zip(cands, sh):
        c["q"] = 0.55 * min(s, 1.2) + 0.45 * max(c["frontal"], 0) + (0.6 if c["rest"] else 0)  # pauses first
    picked = []
    for c in sorted(cands, key=lambda c: -c["q"]):
        if all(abs(c["t"] - p["t"]) >= spacing_s for p in picked):
            picked.append(c)
        if len(picked) >= keep:
            break
    return sorted(picked, key=lambda c: c["t"]), np.array(samples)


def _crop_face(c: dict, size: int = 256) -> np.ndarray:
    x, y, w, h = c["box"]
    cx, cy, s = x + w / 2, y + h * 0.62, max(w, h) * 1.9
    x0, y0 = int(max(cx - s / 2, 0)), int(max(cy - s / 2, 0))
    x1, y1 = int(min(cx + s / 2, W)), int(min(cy + s / 2, H))
    return cv2.resize(c["thumb"][y0:y1, x0:x1], (size, size))


def rank_with_gemini(cands: list[dict], model: str, report: dict) -> list[int]:
    """Ask Gemini which faces make the strongest thumbnail. Returns candidate indexes, best first."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        report["ranking"] = "heuristic (no GEMINI_API_KEY)"
        return sorted(range(len(cands)), key=lambda i: -cands[i]["q"])
    tiles = [_crop_face(c) for c in cands]
    cols = 6
    rows = [np.hstack(tiles[i:i + cols] + [np.zeros_like(tiles[0])] * (cols - len(tiles[i:i + cols])))
            for i in range(0, len(tiles), cols)]
    sheet = np.vstack(rows)
    for i in range(len(tiles)):
        cv2.putText(sheet, str(i), ((i % cols) * 256 + 8, (i // cols) * 256 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (0, 255, 255), 2)
    ok, jpg = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    prompt = ("These numbered tiles are frames of one presenter of a business documentary. Pick the faces that "
              "would make the strongest YouTube thumbnail. Hard requirements, reject any tile that fails one: both "
              "eyes fully open (not closed, not half-closed, not mid-blink); looking straight into the camera (not "
              "away, not down); mouth closed or in a natural smile (never open mid-word, never an odd shape); sharp. "
              "Among those, prefer a clear, readable emotion: intrigue, conviction, a knowing smile, quiet surprise. "
              "Return JSON: {\"best\": [indexes, best first, up to 8], \"why\": short reason}.")
    body = {"contents": [{"parts": [{"text": prompt},
                                    {"inline_data": {"mime_type": "image/jpeg",
                                                     "data": base64.b64encode(jpg.tobytes()).decode()}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        out = json.loads(urllib.request.urlopen(req, timeout=120).read())
        txt = out["candidates"][0]["content"]["parts"][0]["text"]
        best = [int(i) for i in json.loads(txt)["best"] if 0 <= int(i) < len(cands)]
        if not best:
            raise ValueError("empty ranking")
        report["ranking"] = "gemini"
        rest = [i for i in sorted(range(len(cands)), key=lambda i: -cands[i]["q"]) if i not in best]
        return best + rest
    except Exception as e:  # the ranking is a preference, not data: fall back to the measured quality, loudly
        report["ranking"] = f"heuristic (Gemini failed: {e})"
        return sorted(range(len(cands)), key=lambda i: -cands[i]["q"])


def face_ok(crop_bgr: np.ndarray, model: str) -> tuple[bool, str]:
    """Final check of one picked face at full resolution: eyes open, looking at camera, mouth natural."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return True, "not checked (no key)"
    ok, jpg = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    q = ("Check this face for a YouTube thumbnail. Answer JSON {\"eyes_open\": bool, \"looking_at_camera\": bool, "
         "\"mouth_natural\": bool, \"note\": short}. eyes_open is false if the eyes are closed, half-closed or "
         "mid-blink. mouth_natural is false if the mouth is open mid-word or in an odd shape; a closed mouth or a "
         "natural smile is true.")
    body = {"contents": [{"parts": [{"text": q}, {"inline_data": {"mime_type": "image/jpeg",
                                                                   "data": base64.b64encode(jpg.tobytes()).decode()}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        r = json.loads(json.loads(urllib.request.urlopen(req, timeout=90).read())["candidates"][0]["content"]["parts"][0]["text"])
        good = bool(r.get("eyes_open")) and bool(r.get("looking_at_camera")) and bool(r.get("mouth_natural"))
        return good, str(r.get("note", ""))
    except Exception as e:
        return False, f"check failed: {e}"


def cutout(video: Path, t: float, keyer: Keyer) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Full-resolution RGBA cut-out of the presenter at time t, cropped to the person, and the face
    (centre x, eye-line y, width) in cut-out pixels."""
    f = next(_decode(video, 30, 1920, 1080, start=t, frames=1))
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (1920, 1080), 0.6)
    _, faces = det.detect(f)
    if faces is None or not len(faces):
        raise StageError(f"no face at {t:.1f}s for the thumbnail")
    fc = max(faces, key=lambda r: r[2] * r[3])
    eye_y, mouth_y = (fc[5] + fc[7]) / 2, (fc[11] + fc[13]) / 2
    pitch = (fc[9] - eye_y) / max(1.0, mouth_y - eye_y)
    if pitch > 0.62 or fc[14] < 0.85:
        raise StageError(f"face at {t:.1f}s is not facing the camera")
    a = keyer.alpha(f)
    rgb = despill(f.astype(np.float32) / 255)
    ys, xs = np.where(a > 0.05)
    if len(xs) < 1000:
        raise StageError(f"could not key the presenter at {t:.1f}s")
    x0, x1, y0 = xs.min(), xs.max() + 1, ys.min()
    out = np.dstack([np.clip(rgb[y0:, x0:x1] * 255, 0, 255).astype(np.uint8), (a[y0:, x0:x1] * 255).astype(np.uint8)])
    face = (float(fc[0] + fc[2] / 2 - x0), float((fc[5] + fc[7]) / 2 - y0), float(fc[2]))
    return out, face


def grade_scene(img: np.ndarray) -> np.ndarray:
    """Cover 1280x720 and pull the scene into the channel's night palette, darker where the host and words sit."""
    h, w = img.shape[:2]
    s = max(1280 / w, 720 / h)
    img = cv2.resize(img, (int(w * s + .5), int(h * s + .5)), interpolation=cv2.INTER_AREA)
    y0, x0 = (img.shape[0] - 720) // 2, (img.shape[1] - 1280) // 2
    f = img[y0:y0 + 720, x0:x0 + 1280].astype(np.float32) / 255
    lum = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)[..., None]
    shadow = np.array([0.090, 0.122, 0.043], np.float32)       # BGR of the emerald night, lifted a touch
    f = f * 0.82 + (1 - lum) * shadow * 0.35                    # shadows lean emerald
    f = f + lum * np.array([-0.03, 0.0, 0.035], np.float32)     # highlights lean warm
    xx = np.linspace(0, 1, 1280, dtype=np.float32)[None, :, None]
    yy = np.linspace(0, 1, 720, dtype=np.float32)[:, None, None]
    left = 1 - 0.45 * np.clip((0.42 - xx) / 0.42, 0, 1)        # host side
    right = 1 - 0.55 * np.clip((xx - 0.52) / 0.48, 0, 1)       # words side
    vig = 1 - 0.45 * np.clip(np.hypot((xx - .5) / .62, (yy - .5) / .62) - 0.45, 0, 1)
    return np.clip(f * left * right * vig * 255, 0, 255).astype(np.uint8)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--work", default=None)
    a = ap.parse_args(argv)
    job = Path(a.job).resolve()
    cfg = yaml.safe_load(job.read_text(encoding="utf-8"))
    base = job.parent
    tc = cfg.get("thumbnail") or {}
    work = Path(a.work or REPO / "work" / cfg["job"]).resolve()
    out_dir = work / "out" / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)
    video = (base / cfg["inputs"]["video"]).resolve()
    if not video.exists():
        raise StageError(f"input not found: {video}")
    lines = list(tc.get("lines") or [])
    if not lines:
        raise StageError("thumbnail.lines is missing (2-5 words, Ammia)")
    from .run import _find_image
    scenes = [_find_image(base / s) for s in tc.get("scenes") or []]
    if not scenes:
        raise StageError("thumbnail.scenes is missing: generate them with docs/prompts/thumbnails.md")
    report = {}

    gemini_model = cfg.get("transcript", {}).get("gemini_model", "gemini-3.5-flash")
    print("[1/4] shortlist faces", flush=True)
    cands, samples = shortlist(video)
    keyer = Keyer(samples)
    print("[2/4] rank expressions", flush=True)
    if tc.get("at_s"):
        order, picks = [], [float(x) for x in tc["at_s"]]
        report["ranking"] = "given by job (at_s)"
    else:
        order = rank_with_gemini(cands, gemini_model, report)
        picks = [cands[i]["t"] for i in order]
    sheet = np.vstack([np.hstack([_crop_face(c, 180) for c in cands[i:i + 8]] +
                                 [np.zeros((180, 180, 3), np.uint8)] * (8 - len(cands[i:i + 8])))
                       for i in range(0, len(cands), 8)])
    for i, c in enumerate(cands):
        cv2.putText(sheet, f"{c['t']:.1f}s", ((i % 8) * 180 + 6, (i // 8) * 180 + 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 255), 2)
    cv2.imwrite(str(out_dir / "faces_shortlist.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])

    print("[3/4] cut out and grade", flush=True)
    made = []
    with Browser() as br:
        k, pi = 0, 0
        while k < 3:
            if pi >= len(picks):
                if not made:
                    raise StageError("no face passed the checks (eyes open, looking at camera, mouth at rest): "
                                     "pick moments by hand with thumbnail.at_s")
                break
            t = picks[pi]; pi += 1
            try:
                host, (fx, fy, fw) = cutout(video, t, keyer)
            except StageError:
                continue
            if not tc.get("at_s"):
                s = int(fw * 1.8)
                x0, y0 = int(max(fx - s / 2, 0)), int(max(fy - s * 0.45, 0))
                ok, note = face_ok(np.ascontiguousarray(host[y0:y0 + s, x0:x0 + s, :3]), gemini_model)
                report.setdefault("face_checks", []).append({"t": round(t, 2), "ok": ok, "note": note})
                if not ok:
                    continue
            hp = work / f"thumb_host_{k}.png"
            cv2.imwrite(str(hp), host)
            # Thumb C framing: a big face on the left third. Face width 255 px, centre x 285, eyes at y 255.
            z = float(tc.get("face_px", 255)) / fw
            host_css = (f"left:{285 - fx * z:.0f}px;top:{255 - fy * z:.0f}px;"
                        f"width:{host.shape[1] * z:.0f}px;height:{host.shape[0] * z:.0f}px")
            sc = cv2.imread(str(scenes[k % len(scenes)]))
            if sc is None:
                raise StageError(f"cannot read scene {scenes[k % len(scenes)]}")
            sp = work / f"thumb_scene_{k}.jpg"
            cv2.imwrite(str(sp), grade_scene(sc), [cv2.IMWRITE_JPEG_QUALITY, 94])
            print("[4/4] layout", flush=True) if k == 0 else None
            tag = tc.get("tag", "")
            html = fill("thumbnail.html", SCENE=sp.as_uri(), HOST=hp.as_uri(), HOST_CSS=host_css,
                        TAG_HTML=f'<div class="tag">{tag}</div>' if tag else "",
                        LINE1=lines[0], LINE2=lines[1] if len(lines) > 1 else "", GHOST=tc.get("ghost", ""),
                        BRAND=brandkit.name())
            png = br.render_html(html, out_dir / f"thumbnail_{k + 1}.png", 1280, 720, workdir=work)
            made.append({"file": png.name, "presenter_at_s": round(t, 1), "scene": scenes[k % len(scenes)].name})
            k += 1
    report["thumbnails"] = made
    (out_dir / "thumbnails.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    try:
        main()
    except StageError as e:
        print(f"STOPPED: {e}", flush=True)
        raise SystemExit(2)
