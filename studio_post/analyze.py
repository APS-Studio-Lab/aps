"""Stage 2: per-frame face track (position, size, head pitch) and background samples for the keyer."""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from .util import StageError

MODEL = Path(__file__).with_name("face_detection_yunet_2023mar.onnx")
W, H = 640, 360


def face_track(mezz: Path, sample_every: int = 90) -> tuple[np.ndarray, np.ndarray]:
    """Returns (track[n, 9] = cx, cy, w, h, score, pitch, face B, G, R means; samples[k, 360, 640, 3])."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(mezz), "-vf", f"scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (W, H), 0.6)
    rows, samples, i = [], [], 0
    sx = 1920 / W
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        f = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        _, faces = det.detect(f)
        if faces is not None and len(faces):
            fc = max(faces, key=lambda r: r[2] * r[3])
            x, y, w, h = fc[:4]
            eye_y = (fc[5] + fc[7]) / 2
            mouth_y = (fc[11] + fc[13]) / 2
            pitch = (fc[9] - eye_y) / max(1.0, mouth_y - eye_y)
            x0, x1 = int(max(0, x + w * 0.25)), int(min(W, x + w * 0.75))
            y0, y1 = int(max(0, y + h * 0.4)), int(min(H, y + h * 0.75))
            roi = f[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32) / 255 if x1 > x0 and y1 > y0 else np.zeros((1, 3))
            mb, mg, mr = roi.mean(0)
            rows.append([(x + w / 2) * sx, (y + h / 2) * sx, w * sx, h * sx, fc[14], pitch, mb, mg, mr])
        else:
            rows.append([-1, -1, 0, 0, 0, -1, 0, 0, 0])
        if i % sample_every == 0:
            hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
            green = ((hsv[..., 0] > 35) & (hsv[..., 0] < 90) & (hsv[..., 1] > 60) & (hsv[..., 2] > 40)).mean()
            if green > 0.25:  # only green-screen shots teach the keyer (skip graphics already in an export)
                samples.append(f.copy())
        i += 1
    p.wait()
    if i == 0:
        raise StageError("mezzanine decoded no frames")
    track = np.array(rows, np.float32)
    if (track[:, 4] > 0).mean() < 0.5:
        raise StageError("presenter face found in fewer than half the frames; check the footage")
    if not samples:
        raise StageError("no green-screen frames found to train the keyer (is this footage shot on green?)")
    return track, np.array(samples)
