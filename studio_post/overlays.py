"""Overlays: graphics drawn OVER the running video (the presenter keeps talking underneath).

Each type is graphics/overlays/<type>.html with a transparent page and a deterministic window.render(t),
reading its content from window.D. Rendered once per job as an alpha clip (QuickTime RLE) per aspect.

Photos of people come only from Wikimedia Commons with a free licence (or a file the presenter supplies with
its credit line). The credit is drawn on the card. A non-free or unknown licence stops the job: we never
show a photo we may not use.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .util import REPO, StageError

FREE = re.compile(r"^(cc0|public domain|pd|cc[ -]by(-sa)?[ -]\d(\.\d)?)", re.I)
UA = {"User-Agent": "studio-post/1.0 (overlay credits; contact via repository)"}


def commons_photo(title: str, work: Path, width: int = 900) -> tuple[Path, str]:
    """Download a Wikimedia Commons file (e.g. 'File:Herb Kelleher.jpg') and build its credit line."""
    if not title.startswith("File:"):
        title = "File:" + title
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
                                "iiprop": "url|extmetadata", "iiurlwidth": width})
    with urllib.request.urlopen(urllib.request.Request(f"https://commons.wikimedia.org/w/api.php?{q}", headers=UA),
                                timeout=30) as r:
        pages = json.load(r)["query"]["pages"]
    info = next(iter(pages.values())).get("imageinfo")
    if not info:
        raise StageError(f"Wikimedia Commons has no file {title}")
    ii = info[0]
    meta = ii.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    if not FREE.match(lic.strip()):
        raise StageError(f"{title}: licence '{lic or 'unknown'}' is not a free licence; pick another photo")
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip() or "Unknown author"
    artist = re.sub(r"\s+", " ", artist)[:60]
    url = ii.get("thumburl") or ii["url"]
    ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    out = work / f"commons_{abs(hash(title)) % 10**8}{ext}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        out.write_bytes(r.read())
    return out, f"Photo: {artist} / Wikimedia Commons, {lic}"


def wikipedia_photo(article: str, work: Path, lang: str = "en") -> tuple[Path, str]:
    """The lead photo of a Wikipedia article, only if it is a free file on Commons (fair-use images are not)."""
    q = urllib.parse.urlencode({"action": "query", "titles": article, "prop": "pageimages", "piprop": "name",
                                "format": "json", "redirects": 1})
    with urllib.request.urlopen(urllib.request.Request(f"https://{lang}.wikipedia.org/w/api.php?{q}", headers=UA),
                                timeout=30) as r:
        pages = json.load(r)["query"]["pages"]
    name = next(iter(pages.values())).get("pageimage")
    if not name:
        raise StageError(f"the Wikipedia article '{article}' has no lead photo; give a Commons file instead")
    return commons_photo("File:" + name.replace("_", " "), work)


def render(br, kind: str, data: dict, seconds: float, work: Path, tag: str) -> tuple[Path, Path]:
    tpl = REPO / "graphics" / "overlays" / f"{kind}.html"
    if not tpl.exists():
        raise StageError(f"unknown overlay type '{kind}' (no {tpl.name})")
    data = dict(data, seconds=seconds)
    if data.get("commons"):
        f, credit = commons_photo(data.pop("commons"), work)
        data["photo"], data["photo_credit"] = f.resolve().as_uri(), credit
    elif data.get("wikipedia"):
        f, credit = wikipedia_photo(data.pop("wikipedia"), work)
        data["photo"], data["photo_credit"] = f.resolve().as_uri(), credit
    if data.get("photo") and not data.get("photo_credit"):
        raise StageError(f"overlay {tag} ({kind}): a photo needs photo_credit (its source and licence)")
    html = tpl.read_text(encoding="utf-8").replace(
        "<head>", f'<head><base href="{tpl.parent.resolve().as_uri()}/">', 1).replace(
        "/*DATA*/", "window.D=" + json.dumps(data, ensure_ascii=False) + ";")
    page = work / f"overlay_{tag}.html"
    page.write_text(html, encoding="utf-8")
    h = br.capture_overlay(page, work / f"overlay_{tag}_h.mov", 1920, 1080, seconds)
    v = br.capture_overlay(page, work / f"overlay_{tag}_v.mov", 1080, 1920, seconds)
    return h, v
