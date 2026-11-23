#!/usr/bin/env bash
# Pick the next job from Google Drive, render it, push results back. Requires an rclone remote named "gdrive".
set -euo pipefail
ROOT="gdrive:${STUDIO_ROOT:?set the STUDIO_ROOT repository variable to your Drive folder name}"
INBOX="$ROOT/01_Inbox"; RENDERS="$ROOT/02_Renders"; ARCHIVE="$ROOT/99_Archive"
JOB="${1:-}"

if [ -z "$JOB" ]; then
  for d in $(rclone lsf "$INBOX" --dirs-only | sed 's#/$##'); do
    files=$(rclone lsf "$INBOX/$d")
    if echo "$files" | grep -qx "job.yaml" && ! echo "$files" | grep -qx "_failed.txt"; then
      if echo "$files" | grep -qx "_processing.txt"; then
        # a run that was killed (out of memory, timeout) never clears its marker: ignore markers older than 7 h
        age=$(( $(date +%s) - $(date -d "$(rclone lsjson "$INBOX/$d/_processing.txt" | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["ModTime"])')" +%s) ))
        [ "$age" -lt 25200 ] && continue
      fi
      JOB="$d"; break
    fi
  done
fi
if [ -z "$JOB" ]; then echo "No new jobs in the Drive inbox."; exit 0; fi
echo "::add-mask::$JOB"   # public logs: never show the job/episode name
echo "Job picked up."
echo "started $(date -u) run $GITHUB_RUN_ID" | rclone rcat "$INBOX/$JOB/_processing.txt"

mkdir -p "inbox/$JOB" out
rclone copy "$INBOX/$JOB" "inbox/$JOB" --exclude "_*.txt" -q
# shared brand assets (set plates, etc.), referenced from job.yaml as ../../00_Brand/...
rclone copy "$ROOT/00_Brand" "00_Brand" -q 2>/dev/null || echo "No brand kit in Drive (optional)."
set +e
# the full log goes to Drive (private); the public Actions log only shows the stage counters
python -m studio_post.run "inbox/$JOB/job.yaml" --work "work/$JOB" > run.log 2>&1 &
pid=$!
# if the runner dies (out of memory) no later step runs: copy the log and memory use to Drive every 5 minutes
( while kill -0 $pid 2>/dev/null; do
    echo "$(date -u +%H:%M) $(free -m | awk '/Mem/{print "mem used "$3" of "$2" MB"} /Swap/{print "swap "$3" MB"}' | tr '\n' ' ')" >> mem.log
    cat run.log mem.log 2>/dev/null | rclone rcat "$INBOX/$JOB/_live.txt" -q 2>/dev/null || true
    sleep 300
  done ) &
tail -n +1 -f run.log --pid=$pid | grep --line-buffered -E '^\[[0-9]/7\]|^STOPPED' | sed -E 's/:.*//' || true
wait $pid
code=$?
set -e

dest="$RENDERS/$JOB"
rclone copy "work/$JOB/out" "$dest" -q || true
rclone copyto run.log "$dest/run.log"
rclone deletefile "$INBOX/$JOB/_live.txt" -q 2>/dev/null || true
# keep the transcript with the episode so re-renders reuse it (no new Gemini calls)
[ -f "work/$JOB/transcript_cache.json" ] && rclone copyto "work/$JOB/transcript_cache.json" "$INBOX/$JOB/transcript_cache.json" -q || true
rclone deletefile "$INBOX/$JOB/_processing.txt" || true
if [ "$code" -eq 0 ]; then
  rclone moveto "$INBOX/$JOB" "$ARCHIVE/$JOB"
  echo "Done: renders are in 02_Renders."
else
  tail -40 run.log | rclone rcat "$INBOX/$JOB/_failed.txt"
  echo "FAILED (exit $code): see _failed.txt in the job's inbox folder (Drive)"; exit "$code"
fi
