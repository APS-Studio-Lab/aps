"""Print type or a logo into a paper surface inside a photograph (a plate), the way ink sits on old paper.

1. The content (Arabic set by Chromium, transparent PNG) is warped onto the measured surface with a dense
   mesh of small perspective tiles, so lines follow the page's arch or the sheet's curl.
2. It is pushed around by the paper's own relief (wrinkles, ripples), taken from the plate's fine detail.
3. Ink density varies with the paper: fibres, wear, slight bleed; the plate's light and shadow stay on top
   (multiply), so ink in shade is darker and ink on a highlight is lifted.
The result is a new plate image; inserts animate the camera over it like any other plate.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _along(pts: np.ndarray, t: float) -> np.ndarray:
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    d = t * seg[-1]
    i = int(np.clip(np.searchsorted(seg, d), 1, len(pts) - 1))
    k = (d - seg[i - 1]) / max(seg[i] - seg[i - 1], 1e-6)
    return pts[i - 1] + (pts[i] - pts[i - 1]) * k


def surface(kind: str, a: list, b: list, region: tuple[float, float, float, float], v_gamma: float = 1.0):
    """P(u, v) in plate pixels. kind 'rows': a = top edge, b = bottom edge (u runs along them);
    kind 'cols': a = left edge, b = right edge (v runs along them)."""
    A, B = np.array(a, np.float64), np.array(b, np.float64)
    u0, u1, v0, v1 = region

    def P(u: float, v: float) -> np.ndarray:
        uu, vv = u0 + (u1 - u0) * u, v0 + (v1 - v0) * v
        if kind == "rows":
            t, s = _along(A, uu), _along(B, uu)
            return t + (s - t) * vv
        vv = vv ** v_gamma
        l, r = _along(A, vv), _along(B, vv)
        return l + (r - l) * uu
    return P


def bake(plate: Path, content_rgba: np.ndarray, P, out: Path, scale: int = 2, nu: int = 48, nv: int = 36,
         ink=(0.16, 0.12, 0.09), density: float = 0.86, relief_px: float = 2.2, seed: int = 5) -> Path:
    img = cv2.imread(str(plate)).astype(np.float32) / 255
    H0, W0 = img.shape[:2]
    img = cv2.resize(img, (W0 * scale, H0 * scale), interpolation=cv2.INTER_CUBIC)
    H, W = img.shape[:2]
    a_src = content_rgba[..., 3].astype(np.float32) / 255
    ch, cw = a_src.shape

    # 1) dense mesh: each small tile of the content gets its own perspective map onto the surface
    alpha = np.zeros((H, W), np.float32)
    for i in range(nu):
        for j in range(nv):
            x0, x1 = cw * i / nu, cw * (i + 1) / nu
            y0, y1 = ch * j / nv, ch * (j + 1) / nv
            src = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
            dst = np.float32([P(i / nu, j / nv), P((i + 1) / nu, j / nv),
                              P((i + 1) / nu, (j + 1) / nv), P(i / nu, (j + 1) / nv)]) * scale
            bx0, by0 = np.floor(dst.min(0)).astype(int) - 2
            bx1, by1 = np.ceil(dst.max(0)).astype(int) + 2
            bx0, by0, bx1, by1 = max(bx0, 0), max(by0, 0), min(bx1, W), min(by1, H)
            if bx1 <= bx0 or by1 <= by0:
                continue
            M = cv2.getPerspectiveTransform(src, dst - np.float32([bx0, by0]))
            tile = cv2.warpPerspective(a_src, M, (bx1 - bx0, by1 - by0), flags=cv2.INTER_LINEAR)
            mask = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
            cv2.fillConvexPoly(mask, np.round(dst - np.float32([bx0, by0])).astype(np.int32), 1)
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
            region = alpha[by0:by1, bx0:bx1]
            np.maximum(region, tile * mask, out=region)

    # 2) the paper's relief pushes the ink: displacement from the plate's mid-frequency detail (wrinkles)
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    relief = cv2.GaussianBlur(lum, (0, 0), 3 * scale) - cv2.GaussianBlur(lum, (0, 0), 14 * scale)
    gx = cv2.Sobel(relief, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(relief, cv2.CV_32F, 0, 1, ksize=3)
    norm = max(float(np.percentile(np.hypot(gx, gy), 99)), 1e-6)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = relief_px * scale / norm
    alpha = cv2.remap(alpha, xx - gx * k, yy - gy * k, cv2.INTER_LINEAR)

    # 3) ink on old paper: bleed, speckle where ink missed the fibres, wear in patches, more ink in the grain
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.55 * scale)
    rng = np.random.default_rng(seed)
    fine = cv2.GaussianBlur(rng.random((H, W)).astype(np.float32), (0, 0), 0.7 * scale)
    fine = (fine - fine.mean()) / (fine.std() + 1e-6)
    coarse = cv2.resize(rng.random((max(H // 90, 2), max(W // 90, 2))).astype(np.float32), (W, H),
                        interpolation=cv2.INTER_CUBIC)
    grain = cv2.GaussianBlur(lum, (0, 0), 1.0) - cv2.GaussianBlur(lum, (0, 0), 4.0)
    dens = np.clip(0.86 + 0.10 * fine + 0.22 * (coarse - 0.5) - 1.8 * grain, 0.35, 1.0)
    a = np.clip(alpha * dens * density, 0, 1)[..., None]
    ink_bgr = np.array(ink[::-1], np.float32)
    out_img = img * (1 - a) + img * ink_bgr * a * 1.15  # multiply: the plate's light stays on the ink
    out_img = cv2.resize(out_img, (W0 * scale, H0 * scale))
    cv2.imwrite(str(out), np.clip(out_img * 255, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 94])
    return out
