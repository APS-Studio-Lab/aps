"""Contact sheets of a folder of photos: 4x3 thumbnails per sheet, each labelled with its file name.

python scripts/contact_sheet.py <photos dir> <out dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
files = sorted(p for p in src.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic", ".webp"))
W, H, COLS, ROWS = 480, 480, 4, 3
for s in range(0, len(files), COLS * ROWS):
    sheet = Image.new("RGB", (COLS * W, ROWS * (H + 28)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for k, f in enumerate(files[s:s + COLS * ROWS]):
        try:
            im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        except Exception:
            continue
        im.thumbnail((W - 8, H - 8))
        x, y = (k % COLS) * W, (k // COLS) * (H + 28)
        sheet.paste(im, (x + (W - im.width) // 2, y + (H - im.height) // 2))
        d.text((x + 8, y + H + 6), f.stem, fill=(230, 230, 230))
    sheet.save(out / f"sheet_{s // (COLS * ROWS) + 1:02d}.jpg", quality=85)
print("photos:", len(files))
