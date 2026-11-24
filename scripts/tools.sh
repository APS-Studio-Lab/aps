#!/usr/bin/env bash
# ffmpeg (static, with zscale for HDR) and rclone from GitHub releases into ~/.local/bin. Downloads inside
# GitHub are fast and do not depend on the Ubuntu mirrors, whose `apt-get update` sometimes hangs for 30 min.
set -euo pipefail
BIN="$HOME/.local/bin"; mkdir -p "$BIN"; echo "$BIN" >> "$GITHUB_PATH"; export PATH="$BIN:$PATH"
cd "$(mktemp -d)"
if ! command -v ffmpeg >/dev/null || ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q zscale; then
  gh release download latest -R BtbN/FFmpeg-Builds -p 'ffmpeg-master-latest-linux64-gpl.tar.xz'
  tar xf ffmpeg-*.tar.xz && cp ffmpeg-*/bin/ffmpeg ffmpeg-*/bin/ffprobe "$BIN/"
fi
if ! command -v rclone >/dev/null; then
  gh release download -R rclone/rclone -p 'rclone-v*-linux-amd64.zip'
  unzip -q rclone-*.zip && cp rclone-*/rclone "$BIN/"
fi
ffmpeg -hide_banner -version | head -1; rclone version | head -1
