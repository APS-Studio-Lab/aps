"""Stage 4: word timings and word-by-word Arabic caption images (rendered by Chromium)."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .util import Browser, StageError, fill


def transcribe(audio: Path, out_json: Path, model_size: str = "large-v3-turbo", language: str = "ar") -> list[dict]:
    """Word timings with faster-whisper. Raises if the library is missing; never invents captions."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise StageError("captions requested but faster-whisper is not installed") from e
    from .ingest import _pcm

    samples = _pcm(audio, 16000)  # decode with ffmpeg ourselves; avoids PyAV version breakage
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(samples, language=language, word_timestamps=True, vad_filter=True)
    words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
             for seg in segments for w in (seg.words or []) if w.word.strip()]
    if not words:
        raise StageError("transcription returned no words")
    out_json.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    return words


def phrases(words: list[dict], max_words: int = 4, max_s: float = 2.2, gap_s: float = 0.35) -> list[list[dict]]:
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["end"] - cur[0]["start"] > max_s or w["start"] - cur[-1]["end"] > gap_s):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def render_captions(words: list[dict], work: Path) -> list[dict]:
    """One PNG per (phrase, spoken word). Returns timed overlay entries for the compositor."""
    work.mkdir(parents=True, exist_ok=True)
    entries = []
    with Browser() as br:
        for pi, ph in enumerate(phrases(words)):
            for wi, w in enumerate(ph):
                spans = "".join(
                    f'<span class="w{" on" if j == wi else ""}">{html.escape(x["w"])}</span>' for j, x in enumerate(ph))
                png = work / f"cap_{pi:04d}_{wi}.png"
                br.render_html(fill("caption.html", W=1080, H=260, SIZE=64, MAXW=980, WORDS=spans),
                               png, 1080, 260, transparent=True, workdir=work)
                end = ph[wi + 1]["start"] if wi + 1 < len(ph) else w["end"] + 0.15
                entries.append({"start_s": w["start"], "end_s": end, "png": png})
    return entries
