"""Archive inserts: fill an insert template with its data and render it to 16:9 and 9:16 clips.

Templates live in graphics/inserts/<type>.html and read their content from window.D. Plates come from the
brand kit (00_Brand/archive/*), which the render farm downloads from Drive before every job.
"""
from __future__ import annotations

import json
from pathlib import Path

from .util import REPO, StageError, vertical_on

TEMPLATES = REPO / "graphics" / "inserts"
PLATES = REPO / "00_Brand" / "archive"
TYPES = {p.stem for p in TEMPLATES.glob("*.html") if not p.stem.startswith("_")}

REQUIRED = {
    "definition": ["term", "definition"],
    "quote": ["quote", "who", "source"],
    "evidence": ["image", "source"],
    "namecard": ["name", "role"],
    "chapter": ["number", "title"],
    "explainer": ["diagram"],
}


def _page(kind: str, data: dict, work: Path, tag: str) -> Path:
    if kind not in TYPES:
        raise StageError(f"unknown insert type '{kind}' (have: {', '.join(sorted(TYPES))})")
    missing = [k for k in REQUIRED.get(kind, []) if not data.get(k)]
    if missing:
        raise StageError(f"insert '{kind}' is missing: {', '.join(missing)}")
    if not PLATES.exists():
        raise StageError(f"archive plates not found at {PLATES} (Drive: 00_Brand/archive)")
    html = (TEMPLATES / f"{kind}.html").read_text(encoding="utf-8")
    html = html.replace("<head>", f'<head><base href="{TEMPLATES.resolve().as_uri()}/">', 1)
    html = html.replace("/*DATA*/", "window.D = " + json.dumps(data, ensure_ascii=False) + ";", 1)
    out = work / f"insert_{tag}.html"
    out.write_text(html, encoding="utf-8")
    return out


# Surfaces measured in the archive plates (1376 x 768 px). Print lands inside region (u0, u1, v0, v1).
BOOK_TOP = [[826, 186], [850, 176], [905, 174], [1010, 197], [1110, 224], [1212, 252]]
BOOK_BOT = [[592, 474], [650, 487], [750, 508], [850, 530], [960, 556], [1075, 584]]
PRESS_L = [[470, 378], [440, 430], [405, 490], [350, 580], [300, 670], [250, 768]]
PRESS_R = [[1040, 420], [1020, 470], [1003, 530], [990, 600], [970, 680], [948, 768]]
FONTS_URI = (REPO / "brand" / "fonts").resolve().as_uri()


def _type_png(browser, body: str, w: int, h: int, out: Path):
    """Set Arabic type with Chromium onto a transparent canvas (black ink); returns RGBA array."""
    import cv2
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    @font-face{{font-family:Amiri;src:url({FONTS_URI}/Amiri-Bold.ttf);font-weight:700}}
    @font-face{{font-family:AmiriR;src:url({FONTS_URI}/Amiri-Regular.ttf)}}
    html,body{{margin:0;background:transparent;width:{w}px;height:{h}px;overflow:hidden}}
    #c{{width:{w}px;height:{h}px;display:flex;flex-direction:column;align-items:center;justify-content:center;
       direction:rtl;color:#000;padding:0 6%;box-sizing:border-box;text-align:center}}
    </style></head><body><div id="c">{body}</div></body></html>"""
    browser.render_html(html, out, w, h, transparent=True)
    return cv2.imread(str(out), cv2.IMREAD_UNCHANGED)


def _bake(browser, kind: str, data: dict, work: Path, tag: str, vertical: bool) -> str:
    """Print the insert's type/logo into its plate (old ink on old paper). Returns the baked plate's URI."""
    import cv2
    import numpy as np
    from . import printplate
    o = "v" if vertical else "h"
    if kind == "chapter":
        sub = f'<div style="font:100px/1.5 AmiriR;margin-top:44px">{data["subtitle"]}</div>' if data.get("subtitle") else ""
        body = (f'<div style="font:116px Amiri">{data.get("kicker", "الفصل")}</div>'
                f'<div style="font:700 500px/1 Amiri">{data["number"]}</div>'
                f'<div style="width:62%;height:10px;background:#000;margin-top:52px"></div>'
                f'<div style="font:700 {176 if vertical else 224}px/1.28 Amiri;margin-top:60px">{data["title"]}</div>{sub}')
        art = _type_png(browser, body, 2000, 1640, work / f"type_{tag}_{o}.png")
        region = (0.40, 0.94, 0.12, 0.86) if vertical else (0.13, 0.90, 0.10, 0.86)
        P = printplate.surface("rows", BOOK_TOP, BOOK_BOT, region)
        plate = PLATES / "bound_volume.jpeg"
    else:  # ident: the logo and the episode line on the press sheet
        logo_path = Path(data["logo"].replace("file://", "")) if str(data.get("logo", "")).startswith("file://") else None
        if not logo_path or not logo_path.exists():
            raise StageError("ident needs the brand kit logo (00_Brand/logo.png)")
        logo = cv2.imread(str(logo_path), cv2.IMREAD_UNCHANGED)
        if logo is None or logo.shape[2] != 4:
            raise StageError(f"logo must be a PNG with transparency: {logo_path}")
        cw, ch = 2000, 1500
        art = np.zeros((ch, cw, 4), np.uint8)
        lw = int(cw * .56); lh = int(logo.shape[0] * lw / logo.shape[1])
        if lh > ch - 300:
            lh = ch - 300; lw = int(logo.shape[1] * lh / logo.shape[0])
        lg = cv2.resize(logo, (lw, lh), interpolation=cv2.INTER_AREA)
        y, x = max(0, (ch - lh - 280) // 2), (cw - lw) // 2
        art[y:y + lh, x:x + lw, 3] = lg[..., 3]
        if data.get("episode"):
            ep = _type_png(browser, f'<div style="font:700 128px Amiri">{data["episode"]}</div>', cw, 260,
                           work / f"type_{tag}_{o}.png")
            y2 = min(y + lh + 20, ch - 260)
            art[y2:y2 + 260, :, 3] = np.maximum(art[y2:y2 + 260, :, 3], ep[..., 3])
        P = printplate.surface("cols", PRESS_L, PRESS_R, (0.17, 0.83, 0.10, 0.66), v_gamma=1.18)
        plate = PLATES / "press_rollers.jpeg"
    out = printplate.bake(plate, art, P, work / f"baked_{tag}_{o}.jpg")
    return out.resolve().as_uri()


def _over_video(bg: Path, layer: Path, out: Path, w: int, h: int, seconds: float, soft: float = 2.0,
                shift: float = 0.0, start: float = 0.0) -> Path:
    """Composite a transparent motion layer over a moving clip (looped if short, cover-cropped, 30 fps)."""
    import subprocess
    from .util import FPS
    # shift < 0 moves the clip left (shift > 0 right), leaving dark room on the other side for the type;
    # the seam is hidden under a feathered black gradient
    sx = int(round(abs(shift) * w))
    move, extra, grad_in = "", [], ""
    if sx:
        import cv2
        import numpy as np
        move = f",pad={w + sx}:{h}:{0 if shift < 0 else sx}:0:black,crop={w}:{h}:{sx if shift < 0 else 0}:0"
        x = np.arange(w, dtype=np.float32)
        seam = w - sx if shift < 0 else sx
        d = (x - seam) if shift < 0 else (seam - x)          # > 0 on the empty side
        a_ = np.clip((d + sx * 0.45) / (sx * 0.6), 0, 1)      # feather starts inside the clip
        g = np.zeros((h, w, 4), np.uint8)
        g[..., 3] = (a_ * 255).astype(np.uint8)[None, :]
        gp = out.with_suffix(".grad.png")
        cv2.imwrite(str(gp), g)
        extra = ["-i", str(gp)]
        grad_in = "[b0][2:v]overlay=0:0[b];"
    vf = (f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},"
          f"setsar=1,gblur=sigma={soft:.1f},eq=saturation=0.92{move},format=rgb24[{'b0' if sx else 'b'}];"
          f"{grad_in}[b][1:v]overlay=0:0:format=auto,format=yuv420p[o]")
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(bg), "-i", str(layer)] + extra +
                       ["-filter_complex", vf, "-map", "[o]", "-t", f"{seconds:.3f}", "-an",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "14", str(out)], capture_output=True)
    if p.returncode:
        raise StageError(f"compositing over {bg.name} failed: {p.stderr.decode(errors='replace')[-400:]}")
    return out


def render(browser, kind: str, data: dict, seconds: float, work: Path, tag: str) -> tuple[Path, Path]:
    data = dict(data, seconds=seconds)
    bg = data.pop("bg_video", None)
    if bg:  # a moving archive clip behind a transparent graphics layer
        bg = Path(str(bg).replace("file://", ""))
        if not bg.exists():
            raise StageError(f"insert '{kind}': motion clip not found: {bg}")
    outs = []
    for vertical, (w, h) in ((False, (1920, 1080)), (True, (1080, 1920))):
        if vertical and not vertical_on():
            outs.append(None)
            continue
        d = dict(data)
        o = "v" if vertical else "h"
        if kind == "chapter" and not bg:
            d["baked"] = _bake(browser, kind, data, work, tag, vertical)
        page = _page(kind, d, work, f"{tag}_{o}")
        if not vertical and kind == "explainer" and data.get("pen_sound", True):
            from . import pensfx  # the pen's scratch under each stroke and word (mixed in by the pipeline)
            ev = pensfx.events_from_page(browser, page, w, h)
            if ev:
                pensfx.render(ev, seconds, work / f"insert_{tag}_pen.wav", float(data.get("pen_db", -15)))
        if bg:
            layer = browser.capture_overlay(page, work / f"insert_{tag}_{o}_layer.mov", w, h, seconds)
            outs.append(_over_video(bg, layer, work / f"insert_{tag}_{o}.mp4", w, h, seconds,
                                    float(data.get("bg_soft", 2.0)) * w / 1920,
                                    0.0 if vertical else float(data.get("bg_shift", 0.0)),
                                    float(data.get("bg_start", 0.0))))
        else:
            outs.append(browser.capture_animation(page, work / f"insert_{tag}_{o}.mp4", w, h, seconds))
    return outs[0], outs[1]
