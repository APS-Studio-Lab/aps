"""Print a page onto a sheet of paper that is visible in footage, following the sheet's REAL edges.

Instead of forcing the page into a 4-corner perspective, every frame we find the bright sheet, read its left
and right edges row by row and the line where it leaves the rollers, and stretch each line of the page
between the edges. Skew, taper and bend of the sheet carry the page with them. Distance along the sheet uses
the sheet's own width as the ruler (a constant-width sheet looks narrower where it is further away), so the
page foreshortens exactly as the paper does. The sheet's travel comes from optical flow, so the print rides
with the paper and stops when it stops.
"""
from __future__ import annotations

import cv2
import numpy as np


def sheet_edges(frame: np.ndarray, seed: tuple[int, int], thr: int = 135, prev=None, smooth: float = 0.6):
    """(top_y(x) line coeffs, rows, left(rows), right(rows)) of the bright sheet that contains `seed`."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    m = (g > thr).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab = cv2.connectedComponents(m)
    sheet = (lab == lab[seed[1], seed[0]]).astype(np.uint8)
    sheet = cv2.morphologyEx(sheet, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    h, w = sheet.shape
    rows = np.arange(h)
    any_ = sheet.any(1)
    left = np.where(any_, sheet.argmax(1), -1).astype(np.float32)
    right = np.where(any_, w - 1 - sheet[:, ::-1].argmax(1), -1).astype(np.float32)
    top = int(rows[any_][0]) if any_.any() else 0
    ok = any_ & (rows > top + 6)
    # straight-ish edges: robust quadratic fit of x against y
    def fit(x):
        y = rows[ok]; xx = x[ok]
        c = np.polyfit(y, xx, 2)
        r = np.abs(np.polyval(c, y) - xx)
        keep = r < np.percentile(r, 80) + 2
        return np.polyfit(y[keep], xx[keep], 2)
    cl, cr = fit(left), fit(right)
    # the nip: first sheet row per column, between the edges, fitted as a line
    cols = np.arange(int(np.polyval(cl, top + 20)) + 10, int(np.polyval(cr, top + 20)) - 10)
    cols = cols[(cols >= 0) & (cols < w)]
    ty = sheet[:, cols].argmax(0).astype(np.float32)
    ct = np.polyfit(cols, ty, 1)
    cur = (ct, cl, cr)
    if prev is not None:  # temporal smoothing against flicker of the threshold
        cur = tuple(smooth * p + (1 - smooth) * c for p, c in zip(prev, cur))
    return cur


def print_page(frame: np.ndarray, page_rgba: np.ndarray, edges, travel: float, page_top: float,
               fore: float = 1.6, margin: float = 0.05, opacity: float = 1.0) -> np.ndarray:
    """Lay the page (RGBA, ink in alpha) on the sheet. Units along the sheet = sheet widths.
    page_top: where the page's top sits along the sheet at travel 0 (negative = still under the rollers)."""
    ct, cl, cr = edges
    h, w = frame.shape[:2]
    ys = np.arange(h, dtype=np.float32)
    L, R = np.polyval(cl, ys), np.polyval(cr, ys)
    width = np.maximum(R - L, 1.0)
    xs = np.arange(w, dtype=np.float32)
    top_x = np.polyval(ct, xs)                       # nip line y at each x
    # distance along the sheet from the nip, per row, in sheet widths (narrower = further = more paper per px)
    cum = np.cumsum(fore / width)
    # lines of the page run parallel to the nip: measure along the sheet from the nip at each column
    V = cum[:, None] - np.interp(top_x, ys, cum)[None, :]
    U = (xs[None, :] - L[:, None]) / width[:, None]              # 0..1 across the sheet
    ph, pw = page_rgba.shape[:2]
    page_w = 1 - 2 * margin
    page_h = page_w * ph / pw
    pu = (U - margin) / page_w * pw
    pv = (V - (page_top + travel)) / page_h * ph
    inside = (U > 0) & (U < 1) & (ys[:, None] > top_x[None, :] + 1)
    mapx = np.where(inside, pu, -10).astype(np.float32)
    mapy = np.where(inside, pv, -10).astype(np.float32)
    warped = cv2.remap(page_rgba, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    a = cv2.GaussianBlur(warped[..., 3].astype(np.float32) / 255, (0, 0), 0.6) * opacity
    f = frame.astype(np.float32) / 255
    lum = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    dens = np.clip(0.55 + 0.6 * lum, 0, 1)[..., None]
    ink = np.float32([0.08, 0.12, 0.16])
    printed = f * (1 - dens * (1 - ink))
    out = f * (1 - a[..., None]) + printed * a[..., None]
    return np.clip(out * 255, 0, 255).astype(np.uint8)


def sheet_travel(frames: list[np.ndarray], edges: list, fore: float = 1.6) -> list[float]:
    """How far the sheet has run (sheet widths) at each frame, from median optical flow on the sheet."""
    out, acc = [0.0], 0.0
    for a in range(len(frames) - 1):
        ct, cl, cr = edges[a]
        g0 = cv2.cvtColor(frames[a], cv2.COLOR_BGR2GRAY)
        g1 = cv2.cvtColor(frames[a + 1], cv2.COLOR_BGR2GRAY)
        h, w = g0.shape
        mask = np.zeros_like(g0)
        ys = np.arange(h)
        L, R = np.polyval(cl, ys), np.polyval(cr, ys)
        top = int(np.polyval(ct, (L[h // 2] + R[h // 2]) / 2)) + 25
        for y in range(top, h - 10, 4):
            mask[y:y + 4, int(L[y]) + 20:int(R[y]) - 20] = 255
        p = cv2.goodFeaturesToTrack(g0, 300, 0.003, 8, mask=mask, blockSize=7)
        dv = 0.0
        if p is not None and len(p) > 8:
            q, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, p, None, winSize=(31, 31), maxLevel=4)
            ok = st.ravel() == 1
            if ok.sum() > 8:
                y0 = p[ok][:, 0, 1]
                dy = (q - p)[ok][:, 0, 1]
                wid = np.polyval(cr, y0) - np.polyval(cl, y0)
                dv = float(np.median(dy * fore / np.maximum(wid, 1)))
        acc += dv
        out.append(acc)
    return out
