"""Shared helpers: subprocess, probing, HTML rendering through Chromium."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from string import Template

REPO = Path(__file__).resolve().parent.parent
FONTS = REPO / "brand" / "fonts"
TEMPLATES = REPO / "brand" / "templates"
FPS = 30


class StageError(RuntimeError):
    """Raised when a stage cannot produce a real result. Never swallow it."""


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if res.returncode != 0:
        raise StageError(f"command failed: {' '.join(cmd[:6])} ...\n{res.stderr[-2000:]}")
    return res


def ffprobe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout
    return json.loads(out)


def video_stream(info: dict) -> dict:
    for s in info["streams"]:
        if s["codec_type"] == "video":
            return s
    raise StageError("no video stream found")


def fill(template_name: str, **values) -> str:
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    values.setdefault("FONTS", FONTS.as_uri())
    return Template(text).substitute(**{k: str(v) for k, v in values.items()})


def chrome_path() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None  # let Playwright use its bundled Chromium


class Browser:
    """Context manager around one headless Chromium for many renders."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        exe = chrome_path()
        kw = {"args": ["--no-sandbox"]}
        if exe:
            kw["executable_path"] = exe
        self.browser = self._pw.chromium.launch(**kw)
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()

    def render_html(self, html: str, out: Path, width: int, height: int, transparent: bool = False, workdir: Path | None = None) -> Path:
        workdir = workdir or out.parent
        page_file = workdir / (out.stem + ".html")
        page_file.write_text(html, encoding="utf-8")
        page = self.browser.new_page(viewport={"width": width, "height": height})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(out), omit_background=transparent)
        page.close()
        return out

    def capture_animation(self, html_file: Path, out: Path, width: int, height: int, seconds: float) -> Path:
        """Render a page exposing window.render(t) to an H.264 clip, frame by frame."""
        n = int(round(seconds * FPS))
        ff = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(out)],
            stdin=subprocess.PIPE,
        )
        page = self.browser.new_page(viewport={"width": width, "height": height})
        page.goto(html_file.resolve().as_uri())
        page.wait_for_timeout(600)
        if not page.evaluate("typeof window.render === 'function'"):
            raise StageError(f"{html_file} does not define window.render(t)")
        for i in range(n):
            page.evaluate(f"window.render({i / FPS})")
            ff.stdin.write(page.screenshot(type="png"))
        page.close()
        ff.stdin.close()
        if ff.wait() != 0:
            raise StageError(f"ffmpeg failed encoding {out}")
        return out
