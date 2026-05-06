#!/usr/bin/env bash
set -euo pipefail

# Migrate raw screen recorder session directories from:
#   logs/session_YYYYMMDD_HHMMSS
# to:
#   logs/screen/sessions/session_YYYYMMDD_HHMMSS
#
# This is idempotent: if there are no root session_* directories, it exits cleanly.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
log_dir="${1:-$repo_root/logs}"
dest_dir="$log_dir/screen/sessions"

if [[ ! -d "$log_dir" ]]; then
  echo "No logs directory found at: $log_dir"
  exit 0
fi

mkdir -p "$dest_dir"

mapfile -t session_dirs < <(find "$log_dir" -maxdepth 1 -type d -name 'session_*' | sort)

if [[ ${#session_dirs[@]} -eq 0 ]]; then
  echo "No root session_* directories to migrate."
  exit 0
fi

for session_dir in "${session_dirs[@]}"; do
  session_name="$(basename "$session_dir")"
  target="$dest_dir/$session_name"

  if [[ -e "$target" ]]; then
    echo "Refusing to overwrite existing destination: $target" >&2
    echo "Source left in place: $session_dir" >&2
    exit 1
  fi
done

for session_dir in "${session_dirs[@]}"; do
  mv "$session_dir" "$dest_dir/"
done

echo "Migrated ${#session_dirs[@]} screen session directories to: $dest_dir"
