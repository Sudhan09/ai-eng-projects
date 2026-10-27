#!/usr/bin/env bash
# Pull every project's new commits into this repo (history kept), refresh flowmap and notes, commit.
set -e
cd "$(dirname "$0")"
WS=..
for name in logparse async-batch-fetcher aiofetch; do
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
mkdir -p projects/interview-notes flowmap
cp -r "$WS/projects/interview-notes/." projects/interview-notes/
rsync -a --delete --exclude exports/ --exclude .git "$WS/flowmap/" flowmap/
git add -A
git diff --cached --quiet || git commit -q -m "Sync flowmap and interview notes"
git log --oneline -1
