#!/usr/bin/env python3
"""Guardian - independent oversight in GitHub Actions (hourly, no AI).

Runs outside the Claude subscription, so it notices an outage even when the agents cannot work.
1. Creates missing labels (tools/labels.json).
2. Fetches routine pulses (issues labelled type:pulse) and the history of constitution/ via `gh`.
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
    repo = os.environ["GITHUB_REPOSITORY"]
    ensure_labels(repo)
    pulses = json.loads(gh("issue", "list", "--repo", repo, "--label", "type:pulse", "--state", "open",
                           "--json", "number,title,body", "--limit", "50"))
    commits = json.loads(gh("api", f"repos/{repo}/commits?path=constitution&per_page=100"))
    limits = kit.load_limits()
    now = kit.now_utc()
    try:
        cap = kit.revenue_status(now.astimezone(kit.tz(limits)).date())
    except (kit.DataError, KeyError, ValueError) as e:
        cap = None
        print(f"warning: revenue cap not computed ({e})", file=sys.stderr)
    result = kit.assess_guardian(pulses, commits, limits, now, (kit.ROOT / kit.STOP_FILE).exists(), cap)
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
    own = [p for p in pulses if p["title"] == PULSE_TITLE]
    if own:
        gh("issue", "edit", str(own[0]["number"]), "--repo", repo, "--body", text)
    else:
        gh("issue", "create", "--repo", repo, "--title", PULSE_TITLE, "--label", "type:pulse", "--body", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
