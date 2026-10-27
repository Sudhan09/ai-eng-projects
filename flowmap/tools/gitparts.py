"""Find a week's Parts in a repo's git history, from commit messages like "feat(w5p1): add the stream endpoint".

Commit messages that name a Part:
- Conventional Commits with the Part as the scope: "feat(w7p1): ...", "fix(w7p1)!: ...", a Stage "test(w16s2): ...",
  the production bridge "feat(pf1p2): ..."; a squash merge's " (#12)" is dropped from the title
- the older "Week 4 Part 2: a seam for the transport" and "Week 4 Part 5 redo: ..."

Rules:
- the newest branch tip gives one line of history; every commit belongs to the week and Part named in its message,
  and a commit that names neither (a fix, a cleanup) belongs to the week and Part before it
- a lettered Part before Part 1 ("Part A") folds into Part 1; "Part 5 redo" is still Part 5
- a Part's code is its last commit
- the newest Part of the newest week is "in progress" until main contains it
- a later week starts from where the week before ended in this repo (its first pill, e.g. "W3"); a week is
  "W7" or "PF1", and "before" means earlier in the history, so W18 work in an old repo never changes W3 or W4
- titles come from the practical's headings ("### Part 2 - Retries that don't make things worse",
  "# Part 2: a seam for the transport", "## Stage 2 - Load the raw tables"), else from the commit message;
  Parts the practical lists that have no commit yet are "not started"
- a Stage is labelled S1, S2, ...
"""

import re
import subprocess

PART_MSG = re.compile(r"\bWeek\s+(\d+)\s+Part\s+(\w+)(\s+redo)?\s*:\s*(.*)", re.I)
CC_MSG = re.compile(r"^\w+\((?:w(\d+)|(pf\d+))(p|s)([0-9a-z]+)\)!?:\s*(.*)", re.I)  # feat(w7p1): / test(w16s2): / feat(pf1p2):
PRACTICAL_HEAD = re.compile(r"^#+\s*(Part|Stage)\s+(\d+)\s*[-:–]\s*(.+?)\s*$")
PR_SUFFIX = re.compile(r"\s*\(#\d+\)\s*$")


def tag(msg):
    """(week, part, title) a commit message names, or None. A week is 7 or "PF1"; a Stage's part is "S2"."""
    m = CC_MSG.search(msg)
    if m:
        week = int(m.group(1)) if m.group(1) else m.group(2).upper()
        part = ("S" if m.group(3).lower() == "s" else "") + m.group(4).upper()
        return week, part, PR_SUFFIX.sub("", m.group(5))
    m = PART_MSG.search(msg)
    return (int(m.group(1)), m.group(2), PR_SUFFIX.sub("", m.group(4))) if m else None


def week_label(week):
    return week if isinstance(week, str) else f"W{week}"


def numbered(part):
    return bool(part) and (part.isdigit() or bool(re.fullmatch(r"S\d+", part)))


def num(label):
    return int(re.sub(r"\D", "", label) or 0)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def newest_tip(repo):
    heads = git(repo, "for-each-ref", "--sort=-committerdate", "--format=%(objectname:short)", "refs/heads").split()
    return heads[0]


def history(repo):
    """(commit, message, date) oldest first, along the newest branch."""
    out = git(repo, "log", "--reverse", "--format=%h%x09%s%x09%ad", "--date=format:%b %d %H:%M", newest_tip(repo))
    return [tuple(line.split("\t", 2)) for line in out.splitlines() if line]


def practical_titles(path):
    titles = {}
    if path:
        for line in open(path, encoding="utf-8"):
            m = PRACTICAL_HEAD.match(line)
            label = ("S" if m and m.group(1) == "Stage" else "") + (m.group(2) if m else "")
            if m and label not in titles:
                titles[label] = m.group(3)[:1].upper() + m.group(3)[1:]
    return titles


def message_title(text):
    first = text.split(",")[0].strip()
    return first[:1].upper() + first[1:]


def parts(repo, week, practical=None):
    """Returns (parts, upcoming, base). parts: [{commit, label, title, date, inProgress}] in order."""
    commits = history(repo)
    tagged = []  # (commit, week, part, message title, date)
    cur_week = cur_part = None
    for commit, msg, date in commits:
        t = tag(msg)
        if t:
            cur_week, cur_part = t[0], t[1]
            tagged.append((commit, cur_week, cur_part, t[2], date))
        else:
            tagged.append((commit, cur_week, cur_part, None, date))
    mine = [t for t in tagged if t[1] == week]
    if not mine:
        return [], [], None
    nums = [t[2] for t in mine if numbered(t[2])]
    first_num = nums[0] if nums else None
    order, last, title_from_msg, dates = [], {}, {}, {}
    for commit, _, part, mtitle, date in mine:
        label = part if numbered(part) or not first_num else first_num
        if label not in order:
            order.append(label)
        last[label] = commit
        dates[label] = date
        if mtitle and label not in title_from_msg and (part == label):
            title_from_msg[label] = message_title(mtitle)
    heads = practical_titles(practical)
    main = git(repo, "rev-parse", "--short", "main").strip() if "main" in git(repo, "branch", "--format=%(refname:short)").split() else None
    newest_week = next(t[1] for t in reversed(tagged) if t[1] is not None)  # the week worked on last
    out = []
    for label in order:
        commit = last[label]
        merged = bool(main) and subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", commit, main]).returncode == 0
        out.append({"commit": commit, "label": label, "title": heads.get(label) or title_from_msg.get(label) or f"Part {label}",
                    "date": dates[label], "inProgress": False if week != newest_week else not merged})
    for p in out[:-1]:
        p["inProgress"] = False  # an earlier Part ended when the next one began
    upcoming = [(n, "not started") for n in sorted(heads, key=num) if n not in order and num(n) > num(order[-1])]
    # a later week starts where the week before ended
    first_i = next(i for i, t in enumerate(tagged) if t[1] == week)
    base = None
    if first_i > 0 and tagged[first_i - 1][1] is not None and tagged[first_i - 1][1] != week:
        prev = tagged[first_i - 1]
        name = f"Week {prev[1]}" if isinstance(prev[1], int) else prev[1]
        base = {"commit": prev[0], "label": week_label(prev[1]), "title": f"where {name} ended", "date": prev[4], "inProgress": False, "base": True}
    return out, upcoming, base


if __name__ == "__main__":
    import json
    import sys

    repo, week = sys.argv[1], int(sys.argv[2]) if sys.argv[2].isdigit() else sys.argv[2].upper()
    practical = sys.argv[3] if len(sys.argv) > 3 else None
    ps, up, base = parts(repo, week, practical)
    print(json.dumps({"base": base, "parts": ps, "upcoming": up}, indent=1))
