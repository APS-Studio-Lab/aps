"""Stage 5: key, grade and composite every kept frame into the 16:9 master and the 9:16 short."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .keyer import Keyer, despill
from .look import Finisher, relight
from .util import FPS, StageError


@dataclass
class Layers:
    bg_h: Path
    bg_v: Path
    logo: Path | None
    overlay_v: Path | None
    host_shift_x: int = 240
    vertical_scale: float = 1.42
    cutaways: list[dict] = field(default_factory=list)  # {start_s, end_s, h: Path, v: Path}
    captions: list[dict] = field(default_factory=list)  # {start_s, end_s, png: Path}
    wrap: float = 0.08
    gains: Path | None = None        # per-frame BGR gains (.npy) from look.take_gains
    light_side: str = "left"         # side of the set's main lamp, in screen space
    bg_blur: float = 3.0
    framing: Path | None = None      # per output frame [zoom, face_x, face_y] (.npy) from joins.plan
    screen: Path | None = None       # per source frame: True = green-screen shot, False = pass through as is
    soft_cut_frames: int = 2         # a removed pause inside a take: dissolve over this many frames (0 = hard cut)


def _load(path: Path, alpha: bool = False) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED if alpha else cv2.IMREAD_COLOR)
    if im is None:
        raise StageError(f"cannot read {path}")
    return im.astype(np.float32) / 255


def _reader(path: Path, w: int, h: int, select: str | None = None, alpha: bool = False):
    vf = [f"select='{select}'"] if select else []
    ch = 4 if alpha else 3
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)] + (["-vf", ",".join(vf), "-fps_mode", "passthrough"] if vf else []) + \
          ["-f", "rawvideo", "-pix_fmt", "bgra" if alpha else "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = w * h * ch

    def frames():
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                p.wait()
                return
            yield np.frombuffer(b, np.uint8).reshape(h, w, ch)
    return frames()


def _writer(path: Path, w: int, h: int):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                             "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)


def _blend_rgba(base: np.ndarray, rgba: np.ndarray, x: int, y: int, opacity: float = 1.0):
    h, w = rgba.shape[:2]
    a = rgba[..., 3:] * opacity
    base[y:y + h, x:x + w] = base[y:y + h, x:x + w] * (1 - a) + rgba[..., :3] * a


def _snap(framing: np.ndarray, i: int) -> bool:
    """A framing jump (a reframe on a cut), as opposed to the smooth per-frame change of a drift."""
    a, b = framing[i - 1], framing[i]
    return bool(abs(b[0] - a[0]) > 0.015 or abs(b[1] - a[1]) > 4 or abs(b[2] - a[2]) > 4)


def _punch(img: np.ndarray, z: float, px: float, py: float) -> np.ndarray:
    """Punch in by z around (px, py): that point stays put, everything else scales. Like a camera zoom."""
    if z <= 1.0001:
        return img
    h, w = img.shape[:2]  # zooming about any point inside the frame never reveals outside it
    px, py = float(np.clip(px, 0, w)), float(np.clip(py, 0, h))
    M = np.float32([[z, 0, px - z * px], [0, z, py - z * py]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def _fit_vertical(img: np.ndarray) -> np.ndarray:
    """A 16:9 frame inside a 9:16 frame: full width in the middle over a blurred, darkened fill of itself."""
    bg = cv2.resize(img, (int(1920 * 16 / 9), 1920), interpolation=cv2.INTER_LINEAR)
    x = (bg.shape[1] - 1080) // 2
    bg = cv2.GaussianBlur(bg[:, x:x + 1080], (0, 0), 30) * 0.45
    fg = cv2.resize(img, (1080, 608), interpolation=cv2.INTER_AREA)
    bg[656:656 + 608] = fg
    return bg


def render_part(mezz: Path, frames: list[int], first_out_index: int, keyer: Keyer, track: np.ndarray,
                layers: Layers, out_h: Path, out_v: Path) -> int:
    """frames: source frame numbers to render, in order. first_out_index: their position in the edit."""
    bgh = cv2.GaussianBlur(_load(layers.bg_h), (0, 0), layers.bg_blur)
    bgv = cv2.GaussianBlur(_load(layers.bg_v), (0, 0), layers.bg_blur)
    gains = np.load(layers.gains) if layers.gains else None
    framing = np.load(layers.framing) if layers.framing else None
    screen = np.load(layers.screen) if layers.screen else None
    fin_h, fin_v = Finisher(1920, 1080), Finisher(1080, 1920)
    wrh, wrv = cv2.GaussianBlur(bgh, (0, 0), 25), cv2.GaussianBlur(bgv, (0, 0), 25)
    logo = _load(layers.logo, True) if layers.logo else None
    if logo is not None:
        logo = cv2.resize(logo, (190, int(logo.shape[0] * 190 / logo.shape[1])))
    ov = _load(layers.overlay_v, True) if layers.overlay_v else None
    # captions: only the ones in this part's time range, loaded while on screen and freed after (memory!)
    t_lo, t_hi = first_out_index / FPS, (first_out_index + len(frames)) / FPS
    caps = sorted(((c["start_s"], c["end_s"], c["png"]) for c in layers.captions
                   if c["end_s"] > t_lo and c["start_s"] < t_hi), key=lambda c: c[0])
    cap_cache: dict = {}

    # cutaway clips: streamed lazily, frame by frame, only while they are on screen
    t0, t1 = first_out_index / FPS, (first_out_index + len(frames)) / FPS
    cut_frames = []
    for c in layers.cutaways:
        if c["end_s"] <= t0 or c["start_s"] >= t1:
            continue
        ov_ = bool(c.get("overlay"))
        cut_frames.append({"start": c["start_s"], "end": c["end_s"], "overlay": ov_,
                           "h": _reader(c["h"], 1920, 1080, alpha=ov_), "v": _reader(c["v"], 1080, 1920, alpha=ov_),
                           "pos": -1, "fh": None, "fv": None})

    sel = "+".join(f"eq(n\\,{f})" for f in frames) if len(frames) < 400 else None
    if sel is None:  # compress into ranges
        ranges, s = [], frames[0]
        for a, b in zip(frames, frames[1:] + [None]):
            if b != a + 1:
                ranges.append(f"between(n\\,{s}\\,{a})")
                s = b
        sel = "+".join(ranges)
    src = _reader(mezz, 1920, 1080, sel)
    wh, wv = _writer(out_h, 1920, 1080), _writer(out_v, 1080, 1920)
    S = layers.vertical_scale
    cx_s = None
    count = 0
    prev_H = prev_V = None
    soft_left, held_H, held_V = 0, None, None
    for k, fr in enumerate(src):
        n_src = frames[k]
        t = (first_out_index + k) / FPS
        if screen is not None and n_src < len(screen) and not screen[n_src]:
            # not a green-screen shot (a graphic, logo card or fade already in a pre-edited export): pass through
            Hf = fr.astype(np.float32) / 255
            Vf = _fit_vertical(Hf)
            cx_s = None
        else:
            a = keyer.alpha(fr)
            f = despill(fr.astype(np.float32) / 255)
            if gains is not None:
                f = f * gains[n_src]
            if track[n_src, 4] > 0:
                f = relight(f, a, track[n_src, 0], track[n_src, 1], track[n_src, 2], layers.light_side)
            f = np.clip(f, 0, 1)

            M = np.float32([[1, 0, layers.host_shift_x], [0, 1, 0]])
            fh, ah = cv2.warpAffine(f, M, (1920, 1080)), cv2.warpAffine(a, M, (1920, 1080))[..., None]
            edge = cv2.GaussianBlur(1 - ah[..., 0], (0, 0), 6)[..., None] * ah
            Hc = fh * ah + bgh * (1 - ah) + wrh * edge * layers.wrap
            z = 1.0
            if framing is not None:
                z, fx, fy = framing[first_out_index + k]
                Hc = _punch(Hc, float(z), float(fx) + layers.host_shift_x, float(fy))
            Hf = fin_h.apply(Hc, first_out_index + k)
            if logo is not None:
                _blend_rgba(Hf, logo, 60, 60, 0.9)

            if framing is not None and first_out_index + k > 0 and _snap(framing, first_out_index + k):
                cx_s = None  # a cut: reframe the short at once instead of drifting across
            cx = track[n_src, 0] if track[n_src, 4] > 0 else (cx_s or 960.0)
            cx_s = cx if cx_s is None else (cx_s + 0.04 * (cx - cx_s) if abs(cx - cx_s) > 25 else cx_s)
            # scale only the strip of the source that lands in the vertical frame (not the whole frame)
            hS, wS = int(round(f.shape[0] * S)), int(round(f.shape[1] * S))
            x0 = int(np.clip(cx_s * S - 540, 0, wS - 1080))
            sx0, sx1 = int(x0 / S), min(f.shape[1], int(np.ceil((x0 + 1080) / S)) + 2)
            fs = cv2.resize(f[:, sx0:sx1], (int(round((sx1 - sx0) * S)), hS), interpolation=cv2.INTER_CUBIC)
            as_ = cv2.resize(a[:, sx0:sx1], (fs.shape[1], hS), interpolation=cv2.INTER_LINEAR)
            ox = max(0, x0 - int(round(sx0 * S)))
            if fs.shape[1] < ox + 1080:  # rounding at the right edge: pad by a pixel or two
                padw = ox + 1080 - fs.shape[1]
                fs = cv2.copyMakeBorder(fs, 0, 0, 0, padw, cv2.BORDER_REPLICATE)
                as_ = cv2.copyMakeBorder(as_, 0, 0, 0, padw, cv2.BORDER_REPLICATE)
            y0 = 1920 - hS
            fv = np.zeros((1920, 1080, 3), np.float32)
            av = np.zeros((1920, 1080), np.float32)
            fv[y0:], av[y0:] = fs[:, ox:ox + 1080], as_[:, ox:ox + 1080]
            AV = av[..., None]
            ev = cv2.GaussianBlur(1 - av, (0, 0), 6)[..., None] * AV
            Vc = fv * AV + bgv * (1 - AV) + wrv * ev * layers.wrap
            if framing is not None and z > 1.0001:
                fx, fy = framing[first_out_index + k][1:]
                Vc = _punch(Vc, 1 + (float(z) - 1) * 0.8, float(fx) * S - x0, y0 + float(fy) * S)
            Vf = fin_v.apply(Vc, first_out_index + k)
        if ov is not None:
            _blend_rgba(Vf, ov, 0, 0)
        for key in [kk for kk, (ce, _) in cap_cache.items() if ce <= t]:
            del cap_cache[key]
        for cs, ce, png_path in caps:
            if cs > t:
                break
            if t < ce:
                if png_path not in cap_cache:
                    cap_cache[png_path] = (ce, _load(png_path, True))
                png = cap_cache[png_path][1]
                _blend_rgba(Vf, png, 0, 1920 - png.shape[0] - 260)

        for c in cut_frames:
            if c["start"] <= t < c["end"]:
                want = int(round((t - c["start"]) * FPS))
                while c["pos"] < want:
                    nh, nv = next(c["h"], None), next(c["v"], None)
                    if nh is None or nv is None:
                        break
                    c["fh"], c["fv"], c["pos"] = nh, nv, c["pos"] + 1
                if c["fh"] is None:
                    continue
                if c["overlay"]:  # a graphic OVER the running video (name card, lower third): its own alpha
                    for F, O in ((Hf, c["fh"]), (Vf, c["fv"])):
                        A = O[..., 3:4].astype(np.float32) / 255
                        F *= 1 - A
                        F += O[..., :3].astype(np.float32) / 255 * A
                    continue
                w = min(1.0, (t - c["start"]) / 0.3, (c["end"] - t) / 0.3)
                Hf = Hf * (1 - w) + c["fh"].astype(np.float32) / 255 * w
                Vf = Vf * (1 - w) + c["fv"].astype(np.float32) / 255 * w

        # soft cut: where the edit removed a pause inside one take, dissolve from the held last frame over
        # a couple of frames, so the small body jump reads as motion instead of a pop
        n = layers.soft_cut_frames
        if n and k > 0 and frames[k] != frames[k - 1] + 1 and prev_H is not None and \
                (framing is None or not _snap(framing, first_out_index + k)):
            soft_left, held_H, held_V = n, prev_H, prev_V
        if soft_left:
            w = 1 - soft_left / (n + 1)
            Hf_out, Vf_out = Hf * w + held_H * (1 - w), Vf * w + held_V * (1 - w)
            soft_left -= 1
        else:
            Hf_out, Vf_out = Hf, Vf
        prev_H, prev_V = Hf, Vf
        Hf, Vf = Hf_out, Vf_out
        wh.stdin.write((Hf * 255).astype(np.uint8).tobytes())
        wv.stdin.write((Vf * 255).astype(np.uint8).tobytes())
        count += 1
    for w in (wh, wv):
        w.stdin.close()
        if w.wait() != 0:
            raise StageError("encoder failed")
    if count != len(frames):
        raise StageError(f"expected {len(frames)} frames, rendered {count}")
    return count
