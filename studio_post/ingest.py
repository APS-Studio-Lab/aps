"""Stage 1: turn camera footage into a constant-30fps Rec.709 mezzanine, and line up the voice track."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .util import FPS, StageError, ffprobe, run, video_stream

TONEMAP = {
    # HLG (phones) and PQ HDR -> SDR Rec.709 with Hable tone mapping
    "arib-std-b67": "zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv",
    "smpte2084": "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv",
}


def make_mezzanine(video: Path, out: Path, report: dict) -> Path:
    info = ffprobe(video)
    vs = video_stream(info)
    transfer = vs.get("color_transfer", "unknown")
    chain = [f"fps={FPS}"]
    if transfer in TONEMAP:
        chain.append(TONEMAP[transfer])
    chain.append("format=yuv420p")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", ",".join(chain), "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", str(out)])
    report["source"] = {
        "file": video.name,
        "resolution": f"{vs['width']}x{vs['height']}",
        "codec": vs.get("codec_name"),
        "transfer": transfer,
        "hdr_tonemapped": transfer in TONEMAP,
        "frame_rate_in": vs.get("avg_frame_rate"),
        "duration_s": round(float(info["format"]["duration"]), 2),
    }
    if vs["height"] < 2160:
        report.setdefault("warnings", []).append(
            f"Source is {vs['height']}p. Vertical crops are enlarged and will look soft; record in 4K.")
    return out


def _pcm(path: Path, rate: int, start: float | None = None, dur: float | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.4f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.4f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if not raw:
        raise StageError(f"no audio decoded from {path.name}")
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def _envelope(a: np.ndarray) -> np.ndarray:  # input at 1 kHz -> 100 Hz log envelope, normalised
    e = np.convolve(np.abs(a), np.ones(50) / 50, "same")[::10]
    e = np.log(e + 1e-4)
    return (e - e.mean()) / (e.std() + 1e-9)


def sync_voice(video: Path, voice: Path, report: dict) -> float:
    """Return where (seconds into the voice file) the video's t=0 sits. Fails if the match is weak."""
    from scipy.signal import fftconvolve

    cam = _envelope(_pcm(video, 1000))
    vo = _envelope(_pcm(voice, 1000))
    if len(vo) < len(cam):
        raise StageError("voice recording is shorter than the video clip; cannot sync")
    corr = fftconvolve(vo, cam[::-1], "valid") / len(cam)
    i = int(np.argmax(corr))
    score = float(corr[i])
    runner_up = float(np.partition(corr, -200)[-200])
    report["sync"] = {"voice_offset_s": round(i / 100, 3), "score": round(score, 3), "runner_up": round(runner_up, 3)}
    if score < 0.5 or score - runner_up < 0.2:
        raise StageError(f"voice sync is unreliable (score {score:.2f}, runner-up {runner_up:.2f}); check the files belong together")
    return i / 100


def program_audio(video: Path, voice: Path | None, offset: float | None, duration: float, out: Path) -> Path:
    """48 kHz mono WAV aligned to the mezzanine timeline: the lapel voice if given, else camera audio."""
    if voice is not None:
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{offset:.4f}", "-t", f"{duration:.4f}", "-i", str(voice),
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(out)])
    else:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-t", f"{duration:.4f}", "-vn",
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(out)])
    return out
