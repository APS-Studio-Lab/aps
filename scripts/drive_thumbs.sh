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
python -m studio_post.thumbs "inbox/$JOB/job.yaml" --work "work/$JOB" > thumbs.log 2>&1
code=$?
set -e
grep -E '^\[[0-9]/4\]|^done|^STOPPED' thumbs.log | sed -E 's/:.*//' || true
rclone copy "work/$JOB/out/thumbnails" "$ROOT/02_Renders/$JOB/thumbnails" -q || true
rclone copyto thumbs.log "$ROOT/02_Renders/$JOB/thumbnails/thumbs.log" -q || true
exit $code
