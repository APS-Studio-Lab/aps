"""Post-production job runner.

    python -m studio_post.run jobs/<job>.yaml [--work DIR]

Raw green-screen take (+ optional lapel voice) -> edited, keyed, branded 16:9 master and 9:16 short,
with a QC report. Every stage fails loudly instead of guessing.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from . import brandkit, inserts, joins, analyze, audio, captions, compose, edit, ingest, look, qc, retakes, transcribe
from .keyer import Keyer
from .util import FPS, REPO, Browser, StageError, fill, run


def _path(p: str | None, base: Path) -> Path | None:
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else (base / q).absolute()


def audio_seconds(wav: Path) -> float:
    import wave
    try:
        with wave.open(str(wav)) as w:
            return w.getnframes() / float(w.getframerate())
    except wave.Error:  # float or extensible WAV
        from .util import ffprobe
        return float(ffprobe(wav)["format"]["duration"])


def _bokeh(w: int, h: int, n: int, seed: int) -> str:
    rnd = random.Random(seed)
    out = ""
    for _ in range(n):
        r = rnd.randint(30, 90)
        out += (f'<div class="bok" style="left:{rnd.randint(0, w)}px;top:{rnd.randint(int(h * .1), int(h * .6))}px;'
                f'width:{2 * r}px;height:{2 * r}px;opacity:{rnd.uniform(.25, .7):.2f}"></div>')
    return out


def _find_image(p: Path) -> Path:
    """Accept the plate whatever extension Gemini saved it with (study_16x9.png, .webp, .png.webp, .jpg)."""
    if p.exists():
        return p
    stem = p.name.split(".")[0]
    for cand in sorted(p.parent.glob(stem + ".*")):
        if cand.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return cand
    raise StageError(f"background image not found: {p} (looked for {stem}.png/.jpg/.webp)")


def _cover(src: Path, w: int, h: int, out: Path, zoom: float = 1.0, anchor=(0.5, 0.5), lens_blur: float = 0.0) -> Path:
    """Fit a set plate to the frame: scale-and-crop (zoom > 1 pushes into the room), then an optical
    lens blur (disc kernel, so practical lights turn into round bokeh) to match a presenter standing
    close to the camera."""
    import cv2

    src = _find_image(src)
    im = cv2.imread(str(src))
    if im is None:
        raise StageError(f"cannot read background image {src}")
    if max(im.shape[:2]) < 1600:
        print(f"note: {src.name} is only {im.shape[1]}x{im.shape[0]}; a 2K/4K plate will look sharper", flush=True)
    s = max(w / im.shape[1], h / im.shape[0]) * max(1.0, zoom)
    im = cv2.resize(im, (round(im.shape[1] * s), round(im.shape[0] * s)), interpolation=cv2.INTER_LANCZOS4)
    x0 = int((im.shape[1] - w) * anchor[0])
    y0 = int((im.shape[0] - h) * anchor[1])
    im = im[y0:y0 + h, x0:x0 + w]
    if lens_blur > 0:
        k = int(lens_blur * 2) | 1
        ker = np.zeros((k, k), np.float32)
        cv2.circle(ker, (k // 2, k // 2), k // 2, 1, -1)
        im = cv2.filter2D(im.astype(np.float32), -1, ker / ker.sum())
    cv2.imwrite(str(out), np.clip(im, 0, 255).astype(np.uint8))
    return out


def _part(args):
    mezz, frames, first, samples_path, track_path, layers, out_h, out_v = args
    keyer = Keyer(np.load(samples_path))
    return compose.render_part(Path(mezz), frames, first, keyer, np.load(track_path), layers, Path(out_h), Path(out_v))


def _norm_ar(w: str) -> str:
    import re
    w = re.sub(r"[\u064B-\u0652\u0640]", "", w)                     # tashkeel, tatweel
    w = w.translate(str.maketrans("أإآىةؤئ", "اااىهوي")).replace("ى", "ي")
    return re.sub(r"[^\w]", "", w.lower())


def _find_phrase(words: list[dict], phrase: str) -> float:
    """Start time of the phrase in the transcript. Tolerates small spelling differences between runs."""
    from difflib import SequenceMatcher
    target = [_norm_ar(x) for x in phrase.split() if _norm_ar(x)]
    toks = [_norm_ar(w["w"]) for w in words]
    n, best, best_i = len(target), 0.0, -1
    for i in range(len(toks) - n + 1):
        r = SequenceMatcher(None, " ".join(toks[i:i + n]), " ".join(target)).ratio()
        if r > best:
            best, best_i = r, i
    if best < 0.8:
        raise StageError(f"insert anchor phrase not found in transcript (best match {best:.2f}): {phrase}")
    return words[best_i]["start"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--work", default=None)
    ap.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    a = ap.parse_args(argv)

    job_file = Path(a.job).resolve()
    cfg = yaml.safe_load(job_file.read_text(encoding="utf-8"))
    base = job_file.parent
    name = cfg["job"]
    work = Path(a.work or (REPO / "work" / name)).resolve()
    work.mkdir(parents=True, exist_ok=True)
    out_dir = _path(cfg.get("output_dir"), base) or work / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"job": name, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    t_start = time.time()

    video = _path(cfg["inputs"]["video"], base)
    voice = _path(cfg["inputs"].get("voice"), base)
    for p in [video] + ([voice] if voice else []):
        if not p.exists():
            raise StageError(f"input not found: {p}")
    bgc0 = cfg.get("background") or {}
    for key in ("image_h", "image_v"):
        if bgc0.get(key):
            _find_image(_path(bgc0[key], base))  # fail in seconds, not after the mezzanine

    print("[1/7] mezzanine (tone-map, 30 fps)", flush=True)
    mezz = ingest.make_mezzanine(video, work / "mezz.mp4", report)
    n_frames = int(ingest.ffprobe(mezz)["streams"][0]["nb_frames"])
    duration = n_frames / FPS

    print("[2/7] voice sync", flush=True)
    offset = ingest.sync_voice(video, voice, report) if voice else None
    program = ingest.program_audio(video, voice, offset, duration, work / "program.wav")

    print("[3/7] face track + screen samples", flush=True)
    track, samples = analyze.face_track(mezz)
    track = track[:n_frames]
    np.save(work / "track.npy", track)
    np.save(work / "samples.npy", samples)

    print("[4/7] edit", flush=True)
    edit_cfg = cfg.get("edit", {})
    pretrimmed = edit_cfg.get("mode") == "keep"
    if pretrimmed:  # already cut by hand (e.g. a Filmora export): keep every frame, only treat the joins
        takes = [(0, n_frames - 1)]
        report["edit"] = {"mode": "keep (pre-edited export)", "seconds": round(n_frames / FPS, 1)}
    else:
        takes = edit.speech_frames(program, edit_cfg, n_frames, track, report)
    _, master_wav = audio.cut_and_master(program, takes, work)

    cap_cfg = cfg.get("captions", {"enabled": False})
    tr_cfg = cfg.get("transcript", {})
    words = None
    if cap_cfg.get("enabled") or tr_cfg.get("enabled", True):
        print("[5/7] transcript, retakes, captions", flush=True)
        wf = _path(cap_cfg.get("words_file"), base)
        if wf:
            words = json.loads(wf.read_text(encoding="utf-8"))
        else:
            # Transcripts are kept next to job.yaml (transcript_cache.json) so re-renders cost no Gemini calls.
            # A hand-made one (e.g. from Antigravity) in the same format is used the same way.
            cache = base / "transcript_cache.json"
            dur = round(audio_seconds(work / "voice_cut.wav"), 2)
            utts = None
            if cache.exists() and not tr_cfg.get("refresh"):
                c = json.loads(cache.read_text(encoding="utf-8"))
                if abs(float(c.get("duration_s", dur)) - dur) <= 0.5 and c.get("utterances"):
                    utts = c["utterances"]
                    report["transcript"] = {"engine": f"cached ({c.get('engine', 'manual')})", "utterances": len(utts)}
                else:
                    report.setdefault("warnings", []).append(
                        f"transcript_cache.json ignored: made for {c.get('duration_s')}s of audio, this cut is {dur}s")
            if utts is None:
                utts = transcribe.transcribe(work / "voice_cut.wav", tr_cfg, report)
                (work / "transcript_cache.json").write_text(json.dumps(
                    {"engine": report.get("transcript", {}).get("engine"), "duration_s": dur, "utterances": utts},
                    ensure_ascii=False, indent=1), encoding="utf-8")
            (work / "transcript_raw.json").write_text(json.dumps(utts, ensure_ascii=False, indent=1), encoding="utf-8")
            words = transcribe.to_words(utts)
        if cfg.get("retakes", {}).get("enabled", True) and not pretrimmed:
            cuts = retakes.find_retakes(words)
            if cuts:
                before = sum(f1 - f0 + 1 for f0, f1 in takes) / FPS
                takes = retakes.apply(takes, cuts)
                words = retakes.retime_words(words, cuts)
                _, master_wav = audio.cut_and_master(program, takes, work)
                report["retakes"] = {"removed": len(cuts), "seconds_before": round(before, 2),
                                     "seconds_after": round(sum(f1 - f0 + 1 for f0, f1 in takes) / FPS, 2),
                                     "details": [f"{c['start']:.1f}-{c['end']:.1f}s dropped: {c['dropped'][:80]}" for c in cuts]}
        (work / "transcript.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        (work / "transcript.txt").write_text(" ".join(w["w"] for w in words), encoding="utf-8")
    (work / "edl.txt").write_text("\n".join(f"{f0 / FPS:.3f}\t{(f1 + 1) / FPS:.3f}" for f0, f1 in takes))
    frames = [f for f0, f1 in takes for f in range(f0, f1 + 1)]
    j_cfg = cfg.get("joins", {})
    framing_path = None
    screen_path = None
    if j_cfg.get("enabled", True):
        diff, green = joins.frame_scan(mezz)
        screen = joins.screen_frames(green)
        screen_path = work / "screen.npy"
        np.save(screen_path, screen)
        framing, join_list = joins.plan(frames, track, diff, j_cfg)
        framing_path = work / "framing.npy"
        np.save(framing_path, framing)
        passed = int((~screen[frames]).sum()) if len(screen) >= len(frames) else 0
        if passed:
            report.setdefault("edit", {})["passed_through_s"] = round(passed / FPS, 1)
        joins.soften_audio(master_wav, [j["t"] for j in join_list])
        report["joins"] = {"count": len(join_list),
                           "large": sum(j["severity"] == "large" for j in join_list),
                           "short_segments": sum(j["short_segment"] for j in join_list),
                           "list": [f"{j['t']:.2f}s {j['severity']} ({j['treatment']})" for j in join_list]}
    if cap_cfg.get("enabled"):
        cap_entries = captions.render_captions(words, work / "captions")
    else:
        cap_entries = []
        report.setdefault("warnings", []).append("Captions disabled for this job.")

    print("[6/7] brand layers + graphics", flush=True)
    short = cfg.get("short", {})
    bgc = cfg.get("background", {})
    seed = bgc.get("seed", 3)
    with Browser() as br:
        if bgc.get("image_h"):
            zoom, lb = float(bgc.get("zoom", 1.0)), float(bgc.get("lens_blur", 14))
            anc = (float(bgc.get("anchor_x", 0.5)), float(bgc.get("anchor_y", 0.5)))
            bg_h = _cover(_path(bgc["image_h"], base), 1920, 1080, work / "bg_h.png", zoom, anc, lb)
            bg_v = _cover(_path(bgc.get("image_v") or bgc["image_h"], base), 1080, 1920, work / "bg_v.png",
                          zoom, (0.5, anc[1]), lb * 0.9)
        else:
            bg_h = br.render_html(fill("background.html", W=1920, H=1080, PX="62%", PY="45%", LINE_BOTTOM=160,
                                       BOKEH=_bokeh(1920, 1080, 9, seed)), work / "bg_h.png", 1920, 1080)
            bg_v = br.render_html(fill("background.html", W=1080, H=1920, PX="50%", PY="38%", LINE_BOTTOM=420,
                                       BOKEH=_bokeh(1080, 1920, 8, seed + 2)), work / "bg_v.png", 1080, 1920)
        head = short.get("headline", ["", ""]) + ["", ""]
        overlay = br.render_html(fill("short_overlay.html", TAG=short.get("tag", ""), LINE1=head[0], LINE2=head[1],
                                      BRAND=brandkit.name()), work / "overlay_v.png", 1080, 1920, transparent=True)
        cutaways = []
        for i, c in enumerate(cfg.get("cutaways", []) + cfg.get("inserts", [])):
            if "at_phrase" in c:
                if not words:
                    raise StageError("cutaway anchored to a phrase needs captions/transcript enabled")
                try:
                    at = _find_phrase(words, c["at_phrase"])
                except StageError as e:  # skip only this insert, loudly; never guess a position
                    report.setdefault("inserts_skipped", []).append(f"{c.get('insert', 'graphic')}: {e}")
                    continue
            else:
                at = float(c["at_s"])
            secs = float(c.get("seconds", 6))
            at += float(c.get("offset_s", 0))
            if "insert" in c:  # archive insert: template + data (graphics/inserts/<type>.html)
                data = {k: v for k, v in c.items() if k not in ("insert", "at_phrase", "at_s", "seconds", "offset_s")}
                for key in ("image", "photo", "logo"):  # files from the job folder or the brand kit
                    if data.get(key) and not str(data[key]).startswith(("http", "data:")):
                        f = _path(data[key], base)
                        if not f.exists():
                            raise StageError(f"insert {i} ({c['insert']}): file not found: {f}")
                        data[key] = f.resolve().as_uri()
                h, v = inserts.render(br, c["insert"], data, secs, work, str(i))
            else:
                h = br.capture_animation(_path(c["graphic_h"], REPO), work / f"cut{i}_h.mp4", 1920, 1080, secs)
                v = br.capture_animation(_path(c["graphic_v"], REPO), work / f"cut{i}_v.mp4", 1080, 1920, secs)
            cutaways.append({"start_s": at, "end_s": at + secs, "h": h, "v": v, "kind": c.get("insert", "graphic")})
            report.setdefault("inserts", {})[f"{at:7.2f}s"] = f"{c.get('insert', 'graphic')} ({secs:.1f}s)"
    import cv2
    target_y, tint = look.scene_match(cv2.imread(str(bg_h)).astype(np.float32) / 255)
    if not cfg.get("background", {}).get("image_h"):
        target_y, tint = 0.47, None  # branded graphic set: keep the presenter bright and neutral
    report["look"] = {"face_target": round(target_y, 3), "room_tint": None if tint is None else [round(float(x), 3) for x in tint]}
    gains = look.take_gains(track, takes, target_y=target_y, tint=tint,
                            strength=cfg.get("look", {}).get("normalise_strength", 0.7))
    np.save(work / "gains.npy", gains)
    layers = compose.Layers(bg_h=bg_h, bg_v=bg_v, logo=brandkit.logo(), overlay_v=overlay,
                            cutaways=cutaways, captions=cap_entries, gains=work / "gains.npy",
                            light_side=bgc.get("light_from", "left"),
                            bg_blur=float(bgc.get("blur", 0.5 if bgc.get("image_h") else 3.0)),
                            host_shift_x=int(cfg.get("framing", {}).get("host_shift_x", 240)),
                            framing=framing_path, screen=screen_path)

    print(f"[7/7] composite {len(frames)} frames on {a.workers} workers", flush=True)
    chunk = -(-len(frames) // a.workers)
    jobs = []
    for w in range(a.workers):
        fs = frames[w * chunk:(w + 1) * chunk]
        if fs:
            jobs.append((str(mezz), fs, w * chunk, str(work / "samples.npy"), str(work / "track.npy"), layers,
                         str(work / f"h_{w}.mp4"), str(work / f"v_{w}.mp4")))
    if os.environ.get("STUDIO_PROFILE"):  # profile the compositor in-process (development aid)
        import cProfile, pstats
        pr = cProfile.Profile(); pr.enable(); [_part(j) for j in jobs]; pr.disable()
        pstats.Stats(pr).sort_stats("cumulative").print_stats(28)
        raise SystemExit(0)
    with ProcessPoolExecutor(len(jobs)) as ex:
        done = sum(ex.map(_part, jobs))
    if done != len(frames):
        raise StageError(f"rendered {done} of {len(frames)} frames")

    outputs = {}
    for tag, fname in (("h", "master_16x9.mp4"), ("v", "short_9x16.mp4")):
        lst = work / f"list_{tag}.txt"
        lst.write_text("".join(f"file '{work / f'{tag}_{w}.mp4'}'\n" for w in range(len(jobs))))
        out = out_dir / f"{name}_{fname}"
        if tag == "h" and cfg.get("output", {}).get("master_4k", True):
            # Upscale the master to 2160p: crisper on 4K screens, and YouTube streams 4K uploads at a much
            # higher bitrate, so even 1080p sources look cleaner. Real detail still needs 4K recording.
            out = out_dir / f"{name}_master_4k.mp4"
            vcodec = ["-vf", "scale=3840:2160:flags=lanczos,cas=0.35", "-c:v", "libx264", "-preset", "veryfast",
                      "-crf", "20", "-pix_fmt", "yuv420p"]
        else:
            vcodec = ["-c:v", "copy"]
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(master_wav),
             "-map", "0:v", "-map", "1:a"] + vcodec + ["-af", "apad", "-c:a", "aac", "-b:a", "192k", "-shortest",
             "-movflags", "+faststart", str(out)])
        outputs[out.name.replace(f"{name}_", "")] = out

    qc.check(outputs, report)
    report["render_minutes"] = round((time.time() - t_start) / 60, 1)
    md = qc.write_report(report, work)
    for extra in (md, work / "report.json", work / "edl.txt", work / "transcript.json", work / "transcript.txt"):
        if extra.exists():
            shutil.copy(extra, out_dir / f"{name}_{extra.name}")
    print(md.read_text(encoding="utf-8"))
    if not all(e["pass"] for e in report["qc"].values()):
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except StageError as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        sys.exit(1)
