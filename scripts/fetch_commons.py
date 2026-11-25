#!/usr/bin/env python3
"""Download Wikimedia Commons files (a page of a PDF/DjVu as a large JPEG) with their licence, for the brand kit.
usage: fetch_commons.py OUTDIR "File:A.pdf|page" ...   Refuses anything whose licence is not free."""
import json, re, sys, urllib.parse, urllib.request
from pathlib import Path
UA = {"User-Agent": "studio-post/1.0 (brand kit fetch)"}
FREE = re.compile(r"^(cc0|public domain|pd|no restrictions|cc[ -]by(-sa)?[ -]\d(\.\d)?)", re.I)  # "No restrictions" = Flickr Commons, pre-1929 works
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
import hashlib
for k, item in enumerate(sys.argv[2:], 1):
    title, _, page = item.partition("|")
    q = {"action": "query", "titles": title, "prop": "imageinfo", "format": "json",
         "iiprop": "url|extmetadata", "iiurlwidth": 3000}
    if page:
        q["iiurlparam"] = f"page{page}-3000px"
    with urllib.request.urlopen(urllib.request.Request(
            "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(q), headers=UA), timeout=60) as r:
        ii = next(iter(json.load(r)["query"]["pages"].values()))["imageinfo"][0]
    lic = ii["extmetadata"].get("LicenseShortName", {}).get("value", "")
    if not FREE.match(lic.strip()):
        print(f"item {k}: licence not free, skipped"); continue
    url = ii.get("thumburl") or ii["url"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        (out / f"commons_{hashlib.md5(title.encode()).hexdigest()[:8]}.jpg").write_bytes(r.read())
    (out / f"commons_{hashlib.md5(title.encode()).hexdigest()[:8]}.txt").write_text(f"{title} page {page or 1}\nlicence: {lic}\nsource: {ii['descriptionurl']}\n")
    print(f"item {k}: ok")
