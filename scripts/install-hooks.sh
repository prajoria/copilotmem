#!/usr/bin/env bash
# scripts/install-hooks.sh
#
# One-shot per-clone setup: point Git at the in-repo hooks directory.
# Idempotent — safe to run repeatedly.
#
# See SESSION-START.md §8.5 for what the hooks enforce.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

current="$(git config --local core.hooksPath || true)"
if [[ "$current" == ".githooks" ]]; then
  echo "[install-hooks] Already configured: core.hooksPath = .githooks"
else
  git config --local core.hooksPath .githooks
  echo "[install-hooks] Set core.hooksPath = .githooks"
fi

# On POSIX filesystems, ensure the hook is executable. On Windows Git Bash the
# executable bit is a no-op but chmod is harmless.
chmod +x .githooks/commit-msg 2>/dev/null || true

echo "[install-hooks] Done. Hooks in .githooks/ are now active for this clone."
