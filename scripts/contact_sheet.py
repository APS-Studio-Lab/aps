"""Stack frames/t_<sec>.jpg into frames/sheet.jpg, two per row (pairs = just before / just after a cut)."""
import glob
import subprocess

fs = sorted(glob.glob("frames/t_*.jpg"), key=lambda p: float(p.split("t_")[1][:-4]))
n, cols = len(fs), 2
args = [x for f in fs for x in ("-i", f)]
lay = "|".join(f"{'+'.join(['w0'] * (i % cols)) or 0}_{'+'.join(['h0'] * (i // cols)) or 0}" for i in range(n))
subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", f"xstack=inputs={n}:layout={lay}:fill=black",
                "frames/sheet.jpg"], check=True)
