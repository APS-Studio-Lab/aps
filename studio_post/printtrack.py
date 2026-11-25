"""Print type onto a MOVING surface in real footage (a page of a book, paper running out of a press).

The surface is given as a quad on one reference frame of the clip (corners in clip pixels, clockwise from
top-left of the printed area). It is followed through the clip with optical flow (features inside the quad,
frame-to-frame, homography with RANSAC), so the print rides on the paper as it moves. The type itself is an
animated transparent layer (Chromium, so Arabic shapes correctly), warped onto the surface every frame and
laid down as ink: multiplied into the paper, a touch of bleed, density following the paper's own light.

Several prints can go on one clip (e.g. the logo on the left page, the title on the right page), each with
its own quad, reference frame and time window.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from .util import FPS, StageError


def _frames(clip: Path, w: int, h: int, seconds: float):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", str(clip), "-vf",
                          f"fps={FPS},scale={w}:{h}:flags=lanczos", "-t", f"{seconds:.3f}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    out = []
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3:
            break
        out.append(np.frombuffer(b, np.uint8).reshape(h, w, 3).copy())
    p.wait()
    if not out:
        raise StageError(f"could not read {clip}")
    return out


def track_quad(frames: list[np.ndarray], quad: np.ndarray, ref: int) -> list[np.ndarray]:
    """Quad corners on every frame, following the surface from the reference frame both ways."""
    n = len(frames)
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    quads: list = [None] * n
    quads[ref] = quad.astype(np.float32)

    def step(a: int, b: int):
        q = quads[a]
        mask = np.zeros_like(gray[a])
        cv2.fillConvexPoly(mask, q.astype(np.int32), 255)
        mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
        pts = cv2.goodFeaturesToTrack(gray[a], 400, 0.005, 5, mask=mask, blockSize=7)
        H = None
        if pts is not None and len(pts) >= 8:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray[a], gray[b], pts, None, winSize=(31, 31), maxLevel=4)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(gray[b], gray[a], nxt, None, winSize=(31, 31), maxLevel=4)
            good = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm(back - pts, axis=2).ravel() < 1.0)
            if good.sum() >= 8:
                H, _ = cv2.findHomography(pts[good], nxt[good], cv2.RANSAC, 2.0)
        quads[b] = q if H is None else cv2.perspectiveTransform(q[None], H)[0]

    for k in range(ref, n - 1):
        step(k, k + 1)
    for k in range(ref, 0, -1):
        step(k, k - 1)
    return quads


def feed_offsets(frames: list[np.ndarray], quad: np.ndarray) -> list[float]:
    """Paper running out of a press: how far the paper has travelled (in units of the quad's height) at each
    frame, from the median optical flow inside the quad measured in the paper's own (rectified) plane."""
    Hp = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), quad.astype(np.float32))
    Hi = np.linalg.inv(Hp)
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    mask = np.zeros_like(gray[0])
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    mask = cv2.erode(mask, np.ones((15, 15), np.uint8))
    off, acc = [0.0], 0.0
    for a in range(len(frames) - 1):
        pts = cv2.goodFeaturesToTrack(gray[a], 300, 0.003, 6, mask=mask, blockSize=7)
        dv = 0.0
        if pts is not None and len(pts) >= 8:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray[a], gray[a + 1], pts, None, winSize=(31, 31), maxLevel=4)
            g = st.ravel() == 1
            if g.sum() >= 8:
                p0 = cv2.perspectiveTransform(pts[g], Hi)[:, 0, 1]
                p1 = cv2.perspectiveTransform(nxt[g], Hi)[:, 0, 1]
                dv = float(np.median(p1 - p0))
        acc += dv
        off.append(acc)
    return off


def lay_ink(frame: np.ndarray, layer: np.ndarray, quad: np.ndarray, opacity: float = 1.0,
            feed: tuple | None = None) -> np.ndarray:
    """Warp an RGBA type layer onto the quad and press it into the paper as ink.
    feed=(offset, start, height): the type sits on running paper, `offset` quad-heights down from `start`,
    and only shows below the quad's top edge (where the paper leaves the rollers)."""
    h, w = frame.shape[:2]
    lh, lw = layer.shape[:2]
    if feed is not None:
        off, y0, hh = feed
        Hp = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), quad.astype(np.float32))
        top, bot = y0 + off, y0 + off + hh
        src = np.float32([[0, 0], [lw, 0], [lw, lh], [0, lh]])
        dst = cv2.perspectiveTransform(np.float32([[[0.08, top], [0.92, top], [0.92, bot], [0.08, bot]]]), Hp)[0]
        H = cv2.getPerspectiveTransform(src, dst)
        vis = np.zeros((h, w), np.float32)
        cv2.fillConvexPoly(vis, quad.astype(np.int32), 1.0)
        layer = layer.copy()
        warped_mask = vis
    else:
        warped_mask = None
        H = cv2.getPerspectiveTransform(np.float32([[0, 0], [lw, 0], [lw, lh], [0, lh]]), quad.astype(np.float32))
    warped = cv2.warpPerspective(layer, H, (w, h), flags=cv2.INTER_AREA if lw > w else cv2.INTER_LINEAR,
                                 borderValue=(0, 0, 0, 0)).astype(np.float32) / 255
    a = cv2.GaussianBlur(warped[..., 3], (0, 0), 0.6) * opacity
    if warped_mask is not None:
        a = a * cv2.GaussianBlur(warped_mask, (0, 0), 2.0)
    ink = warped[..., :3] * 0 + np.float32([0.08, 0.12, 0.16])   # old brown-black ink (BGR)
    grain = cv2.GaussianBlur(np.random.default_rng(5).random((h, w)).astype(np.float32), (0, 0), 0.8)
    a = a * np.clip(0.78 + 0.45 * (grain - 0.5) * 2, 0, 1)
    f = frame.astype(np.float32) / 255
    lum = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    dens = np.clip(0.55 + 0.6 * lum, 0, 1)[..., None]          # ink reads stronger where the paper is lit
    printed = f * (1 - dens * (1 - ink))                        # multiply into the paper
    out = f * (1 - a[..., None]) + printed * a[..., None]
    return np.clip(out * 255, 0, 255).astype(np.uint8)


def render(clip: Path, prints: list[dict], layers: list[list[np.ndarray]], out: Path, w: int, h: int,
           seconds: float, grade: float = 0.0) -> Path:
    """prints[i]: {quad: [[x,y]*4] in clip pixels at clip size (cw,ch), clip_size: [cw,ch], ref_s, from_s};
    layers[i]: the RGBA frames of that print's animated type layer (FPS, starting at from_s)."""
    frames = _frames(clip, w, h, seconds)
    tracks, feeds = [], []
    for p in prints:
        cw, ch = p["clip_size"]
        q = np.float32(p["quad"]) * np.float32([w / cw, h / ch])
        if p.get("mode") == "feed":       # paper running out of a press: fixed exit area, type travels with it
            tracks.append([q] * len(frames))
            feeds.append(feed_offsets(frames, q))
        else:
            ref = min(len(frames) - 1, int(round(float(p.get("ref_s", 0)) * FPS)))
            tracks.append(track_quad(frames, q, ref))
            feeds.append(None)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14",
                            "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for k, fr in enumerate(frames):
        for p, tr, lay, fd in zip(prints, tracks, layers, feeds):
            k0 = int(round(float(p.get("from_s", 0)) * FPS))
            i = k - k0
            if 0 <= i < len(lay) and (p.get("until_s") is None or k / FPS < float(p["until_s"])):
                feed = None
                if fd is not None:   # starts hidden under the rollers (negative), rides out with the paper
                    hh = float(p.get("height", 0.55))
                    feed = (fd[k] - fd[k0], float(p.get("start", -0.2)), hh)
                fr = lay_ink(fr, lay[i], tr[k], feed=feed)
        if grade:
            fr = (fr.astype(np.float32) * (1 - grade)).astype(np.uint8)
        enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise StageError("encoding the printed clip failed")
    return out
