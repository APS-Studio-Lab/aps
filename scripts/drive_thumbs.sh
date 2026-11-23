#!/usr/bin/env bash
# Make thumbnails for one inbox job (footage + job.yaml with a `thumbnail:` block + thumbs/scene_*).
# Public logs: no names or paths. Results: 02_Renders/<job>/thumbnails/ in Drive.
set -euo pipefail
ROOT="gdrive:${STUDIO_ROOT:?set the STUDIO_ROOT secret to your Drive folder name}"
JOB="${1:?job folder name required}"
echo "::add-mask::$JOB"
SRC="$ROOT/01_Inbox/$JOB"
rclone lsf "$SRC" >/dev/null 2>&1 || SRC="$ROOT/99_Archive/$JOB"   # also works after the render archived it
mkdir -p "inbox/$JOB"
rclone copy "$SRC" "inbox/$JOB" --exclude "_*.txt" -q
rclone copy "$ROOT/00_Brand" "00_Brand" -q 2>/dev/null || true
set +e
# Stage counters are echoed live (no names); the full log goes to Drive, also after a time-out.
timeout 30m python -u -m studio_post.thumbs "inbox/$JOB/job.yaml" --work "work/$JOB" 2>&1 | tee thumbs.log \
  | grep --line-buffered -E '^\[[0-9]/4\]|^done|^STOPPED' | sed -u -E 's/^(\[[0-9]\/4\]|done|STOPPED)[^(]*(\([0-9]+s\))?.*/\1 \2/'
code=${PIPESTATUS[0]}
[ "$code" = 124 ] && echo "STOPPED (time-out)"
set -e
rclone copy "work/$JOB/out/thumbnails" "$ROOT/02_Renders/$JOB/thumbnails" -q || true
rclone copyto thumbs.log "$ROOT/02_Renders/$JOB/thumbnails/thumbs.log" -q || true
exit $code
