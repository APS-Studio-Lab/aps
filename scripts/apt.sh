#!/usr/bin/env bash
# Install system packages without the occasional 20-30 minute hang of `apt-get update` on hosted runners:
# try the runner's existing package lists first, update (with a time limit) only if that fails.
set -uo pipefail
opts=(-y -qq --no-install-recommends -o Acquire::Retries=3 -o Acquire::http::Timeout=20)
if ! sudo DEBIAN_FRONTEND=noninteractive timeout 600 apt-get install "${opts[@]}" "$@" > /dev/null 2>&1; then
  sudo timeout 300 apt-get update -qq -o Acquire::Retries=3 -o Acquire::http::Timeout=20 || true
  sudo DEBIAN_FRONTEND=noninteractive timeout 900 apt-get install "${opts[@]}" "$@" > /dev/null
fi
