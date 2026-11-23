"""Archive inserts: fill an insert template with its data and render it to 16:9 and 9:16 clips.

Templates live in graphics/inserts/<type>.html and read their content from window.D. Plates come from the
brand kit (00_Brand/archive/*), which the render farm downloads from Drive before every job.
"""
from __future__ import annotations

import json
from pathlib import Path

from .util import REPO, StageError

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


def render(browser, kind: str, data: dict, seconds: float, work: Path, tag: str) -> tuple[Path, Path]:
    data = dict(data, seconds=seconds)
    page = _page(kind, data, work, tag)
    h = browser.capture_animation(page, work / f"insert_{tag}_h.mp4", 1920, 1080, seconds)
    v = browser.capture_animation(page, work / f"insert_{tag}_v.mp4", 1080, 1920, seconds)
    return h, v
