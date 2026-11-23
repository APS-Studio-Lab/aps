"""Green-screen keyer that models the uneven screen instead of keying against one green."""
from __future__ import annotations

import cv2
import numpy as np


def _smoothstep(a: float, b: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


class Keyer:
    def __init__(self, samples_bgr: np.ndarray, lo: float = 0.28, hi: float = 0.72, choke: float = 0.18):
        """samples_bgr: frames (k, 360, 640, 3) spread across the clip, used to model the screen."""
        med = np.median(samples_bgr.astype(np.float32) / 255, axis=0)
        b, g, r = med[..., 0], med[..., 1], med[..., 2]
        gd = g - np.maximum(r, b)
        h, w = gd.shape
        yy, xx = np.mgrid[0:h, 0:w]
        X, Y = xx / w * 2 - 1, yy / h * 2 - 1
        mask = (gd > 0.12) & ~((np.abs(X) < 0.45) & (Y > -0.55))  # screen pixels, presenter area excluded
        if mask.mean() < 0.15:
            raise ValueError("not enough visible green screen to model the background")
        feats = [np.ones_like(X)] + [X ** (i - j) * Y ** j for i in range(1, 5) for j in range(i + 1)]
        F = np.stack(feats, -1)
        plate = np.zeros_like(med)
        for c in range(3):
            coef, *_ = np.linalg.lstsq(F[mask], med[..., c][mask], rcond=None)
            plate[..., c] = F @ coef
        plate = np.clip(plate, 0, 1)
        self.screen_green = cv2.resize(
            np.maximum(plate[..., 1] - np.maximum(plate[..., 2], plate[..., 0]), 0.05), (960, 540),
            interpolation=cv2.INTER_CUBIC)
        self.lo, self.hi, self.choke = lo, hi, choke
        self._k9 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        self._k15 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))

    def alpha(self, frame: np.ndarray) -> np.ndarray:
        H, W = frame.shape[:2]
        sm = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        b, g, r = sm[..., 0], sm[..., 1], sm[..., 2]
        ratio = (g - np.maximum(r, b)) / self.screen_green
        a = 1 - _smoothstep(self.lo, self.hi, ratio)
        core = (a > 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(core, 8)
        if n > 1:
            core = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
        ff = core.copy()
        cv2.floodFill(ff, np.zeros((542, 962), np.uint8), (0, 0), 1)
        filled = core | (ff == 0).astype(np.uint8)
        a = np.maximum(a, cv2.erode(filled, self._k9).astype(np.float32)) * cv2.dilate(filled, self._k15)
        a = cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        a = cv2.ximgproc.guidedFilter(gray, a.astype(np.float32), 6, 1e-3)
        return np.clip((a - self.choke) / (1 - self.choke), 0, 1)


def despill(f: np.ndarray) -> np.ndarray:
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    g2 = np.minimum(g, (r + b) * 0.5 + 0.015)
    s = g - g2
    return np.stack([np.clip(b + s * 0.2, 0, 1), g2, np.clip(r + s * 0.2, 0, 1)], -1)


def grade(f: np.ndarray, exposure: float = 1.16, warmth: float = 0.03) -> np.ndarray:
    f = np.clip(f * exposure, 0, 1)
    f = f - 0.10 * f * (1 - f) * (2 * f - 1)
    f = f ** 0.94
    f[..., 2] *= 1 + warmth
    f[..., 0] *= 1 - warmth
    return np.clip(f, 0, 1)
