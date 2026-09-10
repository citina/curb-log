#!/usr/bin/env python3
"""Publish the laptop's snapshots: pull CI's, rebuild the page data, commit, push.

Run every 30 minutes by launchd (see install_poller.sh). This is Python rather
than shell on purpose: macOS charges a launchd job's file access to the program
it launches, and /bin/bash has no permission for ~/Desktop, where this project
lives — launchd failed a bash version before it ran a line (exit 78, EX_CONFIG,
no output). The Python that runs the poller does have that access, so this runs
under the same interpreter.

This is the only writer of docs/data.json; CI appends to tools/data/ci/ and
nothing else, so the two never conflict. Commits are pathspec-limited, so
nothing else staged in this working copy is ever swept up.
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
