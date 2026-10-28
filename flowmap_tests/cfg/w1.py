KEY, NAME, WEEK = "W1", "logparse", "W1"
# Week 1's commits are not named "Week 1 Part N: ...", so its Parts are set here by hand: each Part is the merge of its
# pull request (the last one also takes the fix and polish PRs). Columns, runs and summaries are worked out.
REPO = "projects/logparse"
PARTS = [
    ("751fd5a", "1", "A typed log record"),
    ("8e91bdf", "2", "Parser settings"),
    ("e9e19d7", "3", "Filters, timing, cache and render"),
    ("8b67a27", "4", "A streaming pipeline"),
    ("d66d1e1", "5", "Typed errors, safe files and a CLI"),
]
COMMIT, BRANCH = "d66d1e1", "main"
