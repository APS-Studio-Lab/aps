"""Technical QC of the finished files. Creative QC (hook, pacing, claims) is a separate, human-gated step."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .util import ffprobe, run


def loudness(path: Path) -> dict:
    err = run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbfs": float(pk[-1]) if pk else None}


def check(outputs: dict[str, Path], report: dict) -> dict:
    res = {}
    for name, path in outputs.items():
        info = ffprobe(path)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        entry = {
            "resolution": f"{v['width']}x{v['height']}",
            "video_s": round(float(v["duration"]), 3),
            "audio_s": round(float(a["duration"]), 3) if a else None,
        }
        entry["av_diff_s"] = round(abs(entry["video_s"] - (entry["audio_s"] or 0)), 3)
        entry.update(loudness(path))
        entry["pass"] = entry["av_diff_s"] <= 0.05 and entry["integrated_lufs"] is not None and \
            abs(entry["integrated_lufs"] + 14) <= 1.0 and entry["true_peak_dbfs"] <= -1.0
        res[name] = entry
    report["qc"] = res
    return res


def write_report(report: dict, work: Path) -> Path:
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [f"# Post-production report: {report.get('job')}", ""]
    for k in ("source", "sync", "edit", "transcript", "retakes", "joins", "inserts", "look"):
        if k in report:
            lines.append(f"## {k.title()}")
            for a, b in report[k].items():
                if isinstance(b, list) and len(b) > 3:
                    lines.append(f"- {a}:")
                    lines += [f"  - {x}" for x in b]
                else:
                    lines.append(f"- {a}: {b}")
            lines.append("")
    lines.append("## QC")
    for name, e in report.get("qc", {}).items():
        lines.append(f"- **{name}** {'PASS' if e['pass'] else 'FAIL'}: {e}")
    for w in report.get("warnings", []):
        lines.append(f"- WARNING: {w}")
    for w in report.get("inserts_skipped", []):
        lines.append(f"- WARNING: insert skipped, anchor not found: {w}")
    md = work / "report.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md
