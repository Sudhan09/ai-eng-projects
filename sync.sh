#!/usr/bin/env bash
# Pull every project's new commits into this repo (history kept), refresh flowmap and notes, commit.
set -e
cd "$(dirname "$0")"
WS=..
for name in logparse async-batch-fetcher aiofetch stream-svc; do
    if ! git remote | grep -qx "$name"; then
        git remote add "$name" "$WS/projects/$name"
    fi
    git fetch -q "$name"
    if [ -d "projects/$name" ]; then
        git merge -q -X subtree="projects/$name/" "$name/main" -m "Sync projects/$name" || true
    else
        git merge -q -s ours --no-commit --allow-unrelated-histories "$name/main"
        git read-tree --prefix="projects/$name/" -u "$name/main"
        git commit -q -m "Add projects/$name with its history"
    fi
done
# the flowmap copy was flowmap/ before it split into flowmap_tests/ and flowmap_playground/: rename it once, history kept
if [ -d flowmap ] && [ ! -d flowmap_tests ]; then git mv flowmap flowmap_tests; fi
mkdir -p projects/interview-notes flowmap_tests flowmap_playground
cp -r "$WS/projects/interview-notes/." projects/interview-notes/
rsync -a --delete --exclude exports/ --exclude .git "$WS/flowmap_tests/" flowmap_tests/
# the playground's code only: your runs and its built page stay on your machine
rsync -a --delete --exclude runs/ --exclude build/ --exclude __pycache__/ --exclude .git "$WS/flowmap_playground/" flowmap_playground/
git add -A
git diff --cached --quiet || git commit -q -m "Sync flowmap and interview notes"
git log --oneline -1
