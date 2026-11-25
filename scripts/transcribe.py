"""Word-timed transcript of one media file: <out>.words.json and a readable <out>.words.txt (one phrase a line).

python scripts/transcribe.py <media> <out_prefix>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio_post.captions import phrases, transcribe  # noqa: E402

media, out = Path(sys.argv[1]), sys.argv[2]
words = transcribe(media, Path(f"{out}.words.json"))
lines = [f"{p[0]['start']:8.2f} {p[-1]['end']:8.2f}  " + " ".join(w["w"] for w in p)
         for p in phrases(words, max_words=10, max_s=6.0, gap_s=0.5)]
Path(f"{out}.words.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("words:", len(words))
