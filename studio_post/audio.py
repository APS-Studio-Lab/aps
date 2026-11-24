"""Cut the program audio on the same frame boundaries as the picture, then master it."""
from __future__ import annotations

from pathlib import Path

from .util import FPS, run


def cut_and_master(program: Path, takes: list[tuple[int, int]], work: Path, lufs: float = -14.0) -> tuple[Path, Path]:
    parts = "+".join(f"between(t,{f0 / FPS:.5f},{(f1 + 1) / FPS - 1e-5:.5f})" for f0, f1 in takes)
    script = work / "aselect.txt"
    script.write_text(f"aselect='{parts}',asetpts=N/SR/TB")
    cut = work / "voice_cut.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(program), "-/filter:a", str(script), str(cut)])
    master = work / "voice_master.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(cut), "-af",
         f"highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2,"
         f"loudnorm=I={lufs}:TP=-1.5:LRA=7", "-ar", "48000", "-c:a", "pcm_s16le", str(master)])
    return cut, master
