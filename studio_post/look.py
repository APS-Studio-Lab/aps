"""Cinematic look: per-take exposure/white-balance normalisation from the face, key/fill relighting of the
presenter to match the set's lamp, and a film finish applied to the whole frame (so person and set read as
one photographed image).

This is colour work on real footage only; faces are never generated or reshaped.
"""
from __future__ import annotations

import cv2
import numpy as np

LAMP = np.array([0.62, 0.82, 1.0], np.float32)  # BGR tint of a warm tungsten practical


def take_gains(track: np.ndarray, takes: list[tuple[int, int]], target_y: float = 0.47,
               target_rg: float = 1.45, target_bg: float = 0.85, strength: float = 0.7,
               tint: np.ndarray | None = None) -> np.ndarray:
    """Per-frame BGR gains so every take lands on the same skin exposure and white balance."""
    gains = np.ones((len(track), 3), np.float32)
    for f0, f1 in takes:
        seg = track[f0:f1 + 1]
        seg = seg[seg[:, 4] > 0]
        if len(seg) < 5:
            continue
        b, g, r = np.median(seg[:, 6]), np.median(seg[:, 7]), np.median(seg[:, 8])
        if g <= 0:
            continue
        y = 0.0722 * b + 0.7152 * g + 0.2126 * r
        k = np.clip(target_y / max(y, 1e-3), 0.7, 1.6)
        gr = np.clip(target_rg / (r / g), 0.85, 1.15)
        gb = np.clip(target_bg / (b / g), 0.85, 1.15)
        vec = np.array([gb, 1.0, gr], np.float32) * k
        gains[f0:f1 + 1] = 1 + strength * (vec - 1)
    if tint is not None:
        gains = gains * tint[None, :]
    return gains


def scene_match(bg_bgr: np.ndarray) -> tuple[float, np.ndarray]:
    """Read the set plate around where the presenter stands; return a face exposure target and a colour
    cast so the presenter sits in the room's light instead of looking pasted on."""
    h, w = bg_bgr.shape[:2]
    roi = bg_bgr[int(h * 0.2):int(h * 0.8), int(w * 0.3):].reshape(-1, 3)
    m = roi.mean(0)
    lum = float(0.0722 * m[0] + 0.7152 * m[1] + 0.2126 * m[2])
    target_y = float(np.clip(0.30 + 0.9 * lum, 0.34, 0.50))
    cast = m / max(float(m.mean()), 1e-3)
    tint = (1 + 0.25 * (cast - 1)).astype(np.float32)  # 25% toward the room's colour
    return target_y, tint / tint[1]


def relight(f: np.ndarray, alpha: np.ndarray, cx: float, cy: float, fw: float, side: str = "left",
            key: float = 0.16, fill: float = 0.32, body_falloff: float = 0.25) -> np.ndarray:
    """Shape light across the presenter: brighter, warmer key side toward the set's lamp, deeper fill side,
    and a gentle fall-off down the body so the eye goes to the face."""
    h, w = f.shape[:2]
    xs = (np.arange(w, dtype=np.float32) - cx) / (2.2 * fw)
    m = np.clip(0.5 - xs if side == "left" else 0.5 + xs, 0, 1)[None, :, None]  # 1 = key side
    ys = np.clip((np.arange(h, dtype=np.float32) - (cy + 1.2 * fw)) / (3.5 * fw), 0, 1)[:, None, None]
    shape = (1 + key * m) * (1 - fill * (1 - m)) * (1 - body_falloff * ys)
    warm = 1 + 0.10 * m * (LAMP - 1)
    out = f * shape * warm
    return out * alpha[..., None] + f * (1 - alpha[..., None])


class Finisher:
    """Filmic curve, split tone, halation, vignette and grain on the full composite."""

    def __init__(self, w: int, h: int, seed: int = 7, grain: float = 0.011, vignette: float = 0.32):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
        self.vig = (1 - vignette * np.clip(r - 0.25, 0, 1) ** 1.6 / 0.75 ** 1.6)[..., None].astype(np.float32)
        rng = np.random.default_rng(seed)
        self.noise = [rng.normal(0, grain, (h // 2, w // 2)).astype(np.float32) for _ in range(12)]
        self.size = (w, h)
        x = np.linspace(0, 1, 256, dtype=np.float32)
        curve = 0.012 + 0.975 * (x ** 1.12)  # slightly lifted blacks
        curve = curve + 0.22 * curve * (1 - curve) * (2 * curve - 1)  # S
        curve = 1 - (1 - curve) ** 1.06  # soft shoulder
        self.lut = np.clip(curve, 0, 1)
        self.lut3 = np.repeat(self.lut.astype(np.float32)[None, :, None], 3, axis=2)
        self.vig3 = np.repeat(self.vig, 3, axis=2)
        self.shadow = np.array([0.016, 0.006, -0.008], np.float32)
        self.light = np.array([-0.045, 0.0, 0.035], np.float32)

    def apply(self, img: np.ndarray, n: int) -> np.ndarray:
        x = np.minimum(np.maximum(img, 0, dtype=np.float32), 1)
        # halation: warm glow around highlights (film emulsion), computed at quarter size (it is a wide blur)
        w, h = self.size
        mx = np.maximum(np.maximum(x[..., 0], x[..., 1]), x[..., 2])
        hi = cv2.resize(mx, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        hi = np.clip((hi - 0.72) / 0.28, 0, 1)
        hi = cv2.resize(cv2.GaussianBlur(hi, (0, 0), 2.5), (w, h), interpolation=cv2.INTER_LINEAR)
        x = cv2.addWeighted(x, 1.0, cv2.merge([hi * 0.018, hi * 0.042, hi * 0.10]), 1.0, 0)
        # filmic tone curve through a 256-entry LUT (cv2.LUT is far faster than fancy indexing)
        idx = cv2.convertScaleAbs(x, alpha=255.0)
        x = cv2.LUT(idx, self.lut3)
        # split tone: teal-ish shadows, amber highlights; slight desaturation
        lum = cv2.transform(x, np.array([[0.0722, 0.7152, 0.2126]], np.float32))
        x = cv2.addWeighted(x, 0.96, cv2.merge([lum, lum, lum]), 0.04, 0)
        x = x + (1 - lum)[..., None] * self.shadow + lum[..., None] * self.light
        x = cv2.multiply(x, self.vig3)
        g = cv2.resize(self.noise[n % len(self.noise)], self.size, interpolation=cv2.INTER_LINEAR)
        g = g * (1.0 - 0.4 * lum)
        x = x + g[..., None]
        return np.minimum(np.maximum(x, 0, out=x), 1, out=x)
