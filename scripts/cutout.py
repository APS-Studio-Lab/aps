"""Green-screen photos -> clean cutouts for thumbnails.

For every photo in IN_DIR writes, into OUT_DIR:
  <name>.png       full-resolution RGBA cutout, cropped to the person (+ margin)
  <name>_grey.jpg  the same cutout on flat mid-grey, for an outside retouch pass
  sheet_NN.jpg     numbered contact sheets of the cutouts on grey
Only keying, edge cleanup and green-spill removal: no grading, no change to the person.
"""
import sys, os, glob, cv2, numpy as np

IN_DIR, OUT_DIR = sys.argv[1], sys.argv[2]
os.makedirs(OUT_DIR, exist_ok=True)


def matte(img):
    f = img.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    gd = g - np.maximum(r, b)
    a = 1 - np.clip((gd - 10) / 50, 0, 1)
    m = (a > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        raise RuntimeError("no person found")
    keep = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    # fill enclosed holes (dark clothes, glasses) but keep real gaps that touch the edge
    inv = 1 - keep
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(inv, 4)
    hh, ww = keep.shape
    for i in range(1, n2):
        x, y, w, h, area = st2[i]
        if x > 0 and y > 0 and x + w < ww and y + h < hh and area < 0.02 * hh * ww:
            keep[lab2 == i] = 1
    core = cv2.erode(keep, np.ones((5, 5), np.uint8))
    a = np.where(core > 0, 1.0, a * cv2.dilate(keep, np.ones((9, 9), np.uint8)))
    a = cv2.GaussianBlur(a, (0, 0), 1.2)
    return np.clip((a - 0.1) / 0.9, 0, 1)


def despill(img):
    f = img.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    lim = np.minimum((r + b) / 2 * 1.06, np.maximum(r, b))
    ng = np.minimum(g, lim)
    lost = g - ng
    return np.clip(np.stack([b + lost * 0.08, ng + lost * 0.12, r + lost * 0.55], -1), 0, 255)


thumbs = []
files = sorted(p for p in glob.glob(os.path.join(IN_DIR, "*")) if p.lower().endswith((".jpg", ".jpeg", ".png", ".heic")))
for i, p in enumerate(files, 1):
    name = os.path.splitext(os.path.basename(p))[0]
    img = cv2.imread(p)
    if img is None:
        print(f"[{i}] unreadable, skipped"); continue
    try:
        a = matte(img)
    except RuntimeError as e:
        print(f"[{i}] {e}"); continue
    ys, xs = np.where(a > 0.05)
    pad = 60
    y0, x0 = max(0, ys.min() - pad), max(0, xs.min() - pad)
    y1, x1 = min(img.shape[0], ys.max() + pad), min(img.shape[1], xs.max() + pad)
    rgb = despill(img)[y0:y1, x0:x1]
    a = a[y0:y1, x0:x1]
    rgba = np.dstack([rgb, a * 255]).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT_DIR, f"{name}.png"), rgba, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    grey = (rgb * a[..., None] + 128 * (1 - a[..., None])).astype(np.uint8)
    cv2.imwrite(os.path.join(OUT_DIR, f"{name}_grey.jpg"), grey, [cv2.IMWRITE_JPEG_QUALITY, 95])
    t = cv2.resize(grey, (300, int(300 * grey.shape[0] / grey.shape[1])), interpolation=cv2.INTER_AREA)
    t = cv2.copyMakeBorder(t[:400], 0, max(0, 400 - t[:400].shape[0]), 0, 0, cv2.BORDER_CONSTANT, value=(128, 128, 128))
    cv2.putText(t, name.replace("IMG_", ""), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    thumbs.append(t)
    print(f"[{i}/{len(files)}] ok")

for s in range(0, len(thumbs), 12):
    group = thumbs[s:s + 12]
    while len(group) % 6:
        group.append(np.full_like(thumbs[0], 128))
    rows = [np.hstack(group[k:k + 6]) for k in range(0, len(group), 6)]
    cv2.imwrite(os.path.join(OUT_DIR, f"sheet_{s // 12 + 1:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
if not thumbs:
    sys.exit("no cutouts made")
