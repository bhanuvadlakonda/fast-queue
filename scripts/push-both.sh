#!/usr/bin/env bash
# Push the current branch to Origin (origin) and GitHub (github).
set -euo pipefail

branch="$(git symbolic-ref --short HEAD)"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "missing remote: origin" >&2
  exit 1
fi

if ! git remote get-url github >/dev/null 2>&1; then
  git remote add github https://github.com/bhanuvadlakonda/fast-queue.git
fi

echo "Pushing ${branch} to origin (Origin)…"
git push -u origin "${branch}"

echo "Pushing ${branch} to github…"
git push -u github "${branch}"
