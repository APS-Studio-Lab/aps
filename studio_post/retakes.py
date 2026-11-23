"""Remove earlier attempts of lines the presenter re-recorded, keeping the last attempt.

Works on the transcript of the cut: when a run of words is repeated (fuzzily) within the next minute,
everything from the earlier attempt up to the start of the retry is removed.
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from .util import FPS

_DIAC = re.compile(r"[ً-ْـ]")


def _norm(tok: str) -> str:
    t = _DIAC.sub("", tok.lower())
    t = re.sub("[إأآا]", "ا", t).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"[^\w]", "", t)


def find_retakes(words: list[dict], window: int = 10, min_words: int = 4, threshold: float = 0.75,
                 horizon_s: float = 60.0) -> list[dict]:
    toks = [_norm(w["w"]) for w in words]
    n, i, found = len(words), 0, []
    while i < n:
        hit = None
        j = i + min_words
        while j < n and words[j]["start"] - words[i]["start"] <= horizon_s:
            L = min(window, j - i, n - j)
            if L >= min_words:
                a, b = " ".join(toks[i:i + L]), " ".join(toks[j:j + L])
                s = min(5, L)
                a5, b5 = " ".join(toks[i:i + s]), " ".join(toks[j:j + s])
                if len(a5) >= 15 and (SequenceMatcher(None, a, b).ratio() >= threshold
                                      or SequenceMatcher(None, a5, b5).ratio() >= 0.8):
                    hit = j
                    break
            j += 1
        if hit is not None:
            found.append({"start": max(0.0, words[i]["start"] - 0.05), "end": words[hit]["start"] - 0.05,
                          "dropped": " ".join(w["w"] for w in words[i:hit]),
                          "kept_retry": " ".join(w["w"] for w in words[hit:hit + 8])})
            i = hit
        else:
            i += 1
    return found


def apply(takes: list[tuple[int, int]], cuts: list[dict]) -> list[tuple[int, int]]:
    """Remove cut-timeline intervals from the takes (source frame ranges)."""
    out, t = [], 0.0
    for f0, f1 in takes:
        d = (f1 - f0 + 1) / FPS
        pieces = [(t, t + d)]
        for c in cuts:
            nxt = []
            for a, b in pieces:
                if c["end"] <= a or c["start"] >= b:
                    nxt.append((a, b))
                else:
                    if c["start"] > a:
                        nxt.append((a, c["start"]))
                    if c["end"] < b:
                        nxt.append((c["end"], b))
            pieces = nxt
        for a, b in pieces:
            g0 = f0 + math.ceil((a - t) * FPS - 1e-6)
            g1 = f0 + math.floor((b - t) * FPS + 1e-6) - 1
            if g1 - g0 + 1 >= 6:  # ignore slivers under 0.2 s
                out.append((g0, g1))
        t += d
    return out


def retime_words(words: list[dict], cuts: list[dict]) -> list[dict]:
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        if any(c["start"] <= mid < c["end"] for c in cuts):
            continue
        shift = sum(c["end"] - c["start"] for c in cuts if c["end"] <= w["start"] + 1e-6)
        out.append({**w, "start": round(w["start"] - shift, 3), "end": round(w["end"] - shift, 3)})
    return out
