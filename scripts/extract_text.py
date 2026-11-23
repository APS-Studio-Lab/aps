"""Flatten one file to plain text: audio/video via Whisper (Arabic), AI Studio prompt JSON, documents via pandoc.

python scripts/extract_text.py <input> <output.txt>
"""
import json
import subprocess
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
ext = src.suffix.lower()


def whisper(p: Path) -> str:
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(p), language="ar", vad_filter=True, condition_on_previous_text=False)
    return "\n".join(f"[{s.start:7.1f}] {s.text.strip()}" for s in segs)


def walk_text(o, out):
    """AI Studio prompt files are JSON; keep every 'text' field with its role, in order."""
    if isinstance(o, dict):
        role = o.get("role")
        if isinstance(o.get("text"), str) and o["text"].strip() and not o.get("isThought"):
            out.append((f"--- {role} ---\n" if role else "") + o["text"].strip())
        for v in o.values():
            if isinstance(v, (dict, list)):
                walk_text(v, out)
    elif isinstance(o, list):
        for v in o:
            walk_text(v, out)


if ext in (".m4a", ".mp3", ".wav", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".ogg"):
    text = whisper(src)
elif ext in (".docx", ".odt", ".rtf", ".html", ".md"):
    text = subprocess.run(["pandoc", str(src), "-t", "plain", "--wrap=none"], capture_output=True, text=True,
                          check=True).stdout
else:
    raw = src.read_text(encoding="utf-8", errors="replace")
    try:
        parts = []
        walk_text(json.loads(raw), parts)
        text = "\n\n".join(parts)
    except json.JSONDecodeError:
        text = raw
dst.write_text(text, encoding="utf-8")
