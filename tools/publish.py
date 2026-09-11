#!/usr/bin/env python3
"""Publish the laptop's snapshots: pull CI's, rebuild the page data, commit, push.

Run every 30 minutes by launchd (see install_poller.sh), under the same Python
as the poller.

If this job ever exits 78 (EX_CONFIG) with an empty log, launchd could not open
its log file. That happened when publish.log had been created from a sandboxed
shell, which tags files com.apple.provenance; logs launchd creates itself carry
com.apple.macl and work. Delete the log and let launchd recreate it — never
create or truncate it by hand.

tools/publisher.txt names the one writer of docs/data.json. While it says
"laptop", this is that writer and CI appends to tools/data/ci/ and nothing else,
so the two never conflict; once it says "ci", this does nothing. Commits are
pathspec-limited, so nothing else staged in this working copy is ever swept up.
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = ["tools/data", "docs/data.json", "tools/archive_cells.json"]
ID = ["-c", "user.name=citina", "-c", "user.email=43682583+citina@users.noreply.github.com"]


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M"), msg, flush=True)


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def main():
    try:
        git("pull", "-q", "--rebase", "--autostash", "origin", "main")
    except subprocess.CalledProcessError as e:
        log("pull failed: " + (e.stderr or "").strip()[:200])
        return 1
    who = open(os.path.join(ROOT, "tools", "publisher.txt")).read().strip()
    if who != "laptop":
        log(f"publisher.txt says {who}; the laptop does not publish")
        return 0
    r = subprocess.run([sys.executable, "build_data.py", "--out", "../docs/data.json"],
                       cwd=os.path.join(ROOT, "tools"), capture_output=True, text=True)
    if r.returncode:
        log("build failed: " + r.stderr.strip()[-200:])
        return 1
    git("add", "--", *PATHS)
    if git("diff", "--cached", "--quiet", "--", *PATHS, check=False).returncode == 0:
        log("nothing new")
        return 0
    git(*ID, "commit", "-q", "-m",
        "laptop snapshots " + time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "--", *PATHS)
    for _ in range(3):
        if (git("pull", "-q", "--rebase", "--autostash", "origin", "main", check=False).returncode == 0
                and git("push", "-q", "origin", "main", check=False).returncode == 0):
            log("published")
            return 0
        time.sleep(20)
    log("push failed after 3 tries")
    return 1


if __name__ == "__main__":
    sys.exit(main())
