#!/usr/bin/env python3
"""Guardian - independent oversight in GitHub Actions (hourly, no AI).

Runs outside the Claude subscription, so it notices an outage even when the agents cannot work.
1. Creates missing labels (tools/labels.json).
2. Fetches routine pulses (issues labelled type:pulse, open and closed) and the history of
   constitution/ via `gh`, back to the owner's latest commit there.
3. Assesses state (kit.assess_guardian): pulses, constitution integrity, optional revenue cap.
4. Sends alerts through Discord (alarm.py); if that fails, opens an `urgent` issue (plan B).
5. Updates its own pulse issue "Pulse: GUARDIAN" (editing an issue body sends no notification).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import alarm
import kit

PULSE_TITLE = "Pulse: GUARDIAN"
PAGE_SIZE = 100
MAX_PAGES = 10  # constitution/ history window: up to 1000 commits per run


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])}: {result.stderr.strip()}")
    return result.stdout


def ensure_labels(repo: str) -> None:
    wanted = json.loads((kit.ROOT / "tools/labels.json").read_text(encoding="utf-8"))
    existing = {e["name"] for e in json.loads(gh("label", "list", "--repo", repo, "--json", "name", "--limit", "200"))}
    for e in wanted:
        if e["name"] not in existing:
            gh("label", "create", e["name"], "--repo", repo, "--color", e["color"], "--description", e["description"])


def constitution_history(repo: str, owner: str) -> tuple[list[dict], bool]:
    """Commits touching constitution/, newest first, up to and including the owner's latest one.

    Returns (commits, complete). complete is False when MAX_PAGES pages were read without reaching
    an owner commit or the end of the history; kit.assess_guardian then raises a SECURITY alert
    instead of trusting the truncated window.
    """
    commits = []
    for page in range(1, MAX_PAGES + 1):
        batch = json.loads(gh("api", f"repos/{repo}/commits?path=constitution&per_page={PAGE_SIZE}&page={page}"))
        commits += batch
        if len(batch) < PAGE_SIZE or any((c.get("author") or {}).get("login") == owner for c in batch):
            return commits, True
    return commits, False


def plan_b(repo: str, a: dict, reason: str) -> None:
    title = f"[{a['code']}] {a['title']}"
    open_issues = json.loads(gh("issue", "list", "--repo", repo, "--state", "open", "--label", "urgent",
                                "--json", "title", "--limit", "100"))
    if any(i["title"] == title for i in open_issues):
        return
    gh("issue", "create", "--repo", repo, "--title", title, "--label", "type:incident", "--label", "urgent",
       "--body", f"{a['body']}\n\n_Guardian: the alert did not reach Discord ({reason})._")


def pulse_text(result: dict) -> str:
    alerts, warnings = result["alerts"], result["warnings"]
    desc = "no remarks" if not alerts and not warnings else f"alerts: {len(alerts)}, warnings: {len(warnings)}"
    lines = [kit.pulse_body("GUARDIAN", "ok", desc, os.environ.get("GITHUB_RUN_ID"))]
    if alerts:
        lines += ["", "#### Alerts"] + [f"- [{a['code']}] {a['title']}" for a in alerts]
    if warnings:
        lines += ["", "#### Warnings (for OPS)"] + [f"- {w}" for w in warnings]
    return "\n".join(lines)


def main() -> int:
    try:
        return run()
    except kit.ConfigError as e:  # e.g. limits.json missing or owner.github empty: fail the job visibly
        print(f"configuration error: {e}", file=sys.stderr)
        return 2


def run() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    limits = kit.load_limits()
    owner = kit.owner_login(limits)  # before any history is read: an empty login would match wrongly
    ensure_labels(repo)
    # Closed pulse issues are read too: closing one must not hide a routine from the silence checks.
    pulses = json.loads(gh("issue", "list", "--repo", repo, "--label", "type:pulse", "--state", "all",
                           "--json", "number,title,body,state,createdAt", "--limit", "100"))
    commits, complete = constitution_history(repo, owner)
    now = kit.now_utc()
    try:
        cap = kit.revenue_status(now.astimezone(kit.tz(limits)).date())
    except (kit.DataError, KeyError, ValueError) as e:
        cap = None
        print(f"warning: revenue cap not computed ({e})", file=sys.stderr)
    result = kit.assess_guardian(pulses, commits, limits, now, (kit.ROOT / kit.STOP_FILE).exists(), cap,
                                 history_complete=complete)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    cfg = alarm.configuration()
    for a in result["alerts"]:
        try:
            code, message = alarm.alarm(cfg, a["code"], a["title"], a["body"], "", "", limits)
        except alarm.NoChannel as e:
            code, message = 2, str(e)
        print(f"[{a['code']}] {message}")
        if code != 0:
            plan_b(repo, a, message)

    text = pulse_text(result)
    own = [p for p in pulses if p["title"] == PULSE_TITLE and str(p.get("state", "open")).lower() == "open"]
    if own:
        gh("issue", "edit", str(own[0]["number"]), "--repo", repo, "--body", text)
    else:
        gh("issue", "create", "--repo", repo, "--title", PULSE_TITLE, "--label", "type:pulse", "--body", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
