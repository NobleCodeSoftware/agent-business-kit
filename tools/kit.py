#!/usr/bin/env python3
"""kit - deterministic helpers for agent-run micro-businesses (Agent Business Kit for Claude Code).

Agents should not hand-format company state. This tool covers: STOP switch, state validation,
sales ledger, optional revenue cap, task leases, intents/results, routine pulses, desk-item
completeness checks and the guardian's assessment.

Standard library only. Exit codes: 0 OK, 1 validation error, 2 configuration/network error,
3 STOP active.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("KIT_ROOT") or Path(__file__).resolve().parent.parent)

LIMITS = "constitution/limits.json"
STOP_FILE = "constitution/STOP"
LEDGER = "finance/ledger.csv"
COSTS = "finance/costs.csv"
CALIBRATION = "knowledge/calibration.csv"

LEDGER_FIELDS = ["no", "date", "channel", "transaction_id", "description", "amount", "currency",
                 "rate", "amount_base", "correction_of"]
COSTS_FIELDS = ["no", "date", "description", "amount_base", "desk_no", "evidence"]
CALIBRATION_FIELDS = ["date", "experiment", "event", "probability", "deadline", "outcome"]

PULSE_ICONS = {"in-progress": "⏳", "ok": "✅", "degraded": "⚠️", "stop": "⛔", "disabled": "💤"}
DESK_TITLE = re.compile(r"^# \[DESK\] .+ — .+ — due (\d{4}-\d{2}-\d{2})\s*$")
DESK_SECTIONS = ["What exactly you need to do", "Why", "Cost and return", "Risks and mitigation",
                 "Alternatives considered", "Recommendation", "If you decline or do not answer",
                 "Attachments"]
# Unfilled template fields such as "<amount>"; ignores HTML comments, <https://...> links and HTML tags.
PLACEHOLDER = re.compile(r"<(?!!--)(?!https?://)([^<>\n]{2,80})>")
HTML_TAG = re.compile(r"^/?(details|summary|br|sub|sup|kbd|b|i|u|code|pre|p|div|span|ul|ol|li|"
                      r"table|thead|tbody|tr|td|th|img|a)(\s[^<>]*)?/?$", re.I)
TAG = re.compile(r"<!--\s*kit:(\w+)\s+(\{.*?\})\s*-->", re.S)
CENT = Decimal("0.01")


class DataError(Exception):
    """Bad input or bad state file (exit code 1)."""


class ConfigError(DataError):
    """Missing configuration or network failure (exit code 2)."""


# ------------------------------------------------------------------ helpers

def now_utc() -> datetime:
    forced = os.environ.get("KIT_NOW")
    return parse_time(forced) if forced else datetime.now(timezone.utc)


def parse_time(text: str) -> datetime:
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_limits() -> dict:
    try:
        return json.loads((ROOT / LIMITS).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"missing file {LIMITS}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"{LIMITS}: invalid JSON ({e})")


def tz(limits: dict | None = None) -> ZoneInfo:
    try:
        return ZoneInfo((limits or load_limits()).get("timezone", "UTC"))
    except Exception:  # unknown zone or missing tz database: fall back to UTC
        return ZoneInfo("UTC")


def today(limits: dict | None = None) -> date:
    return now_utc().astimezone(tz(limits)).date()


def number(text, field: str = "amount") -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError):
        raise DataError(f"{field}: invalid number {text!r}")
    if not value.is_finite():
        raise DataError(f"{field}: invalid number {text!r}")
    return value


def read_csv(rel: str, fields: list[str]) -> list[dict]:
    path = ROOT / rel
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != fields:
            raise DataError(f"{rel}: header {reader.fieldnames} instead of {fields}")
        return list(reader)


def tags(text: str) -> list[tuple[str, dict]]:
    out = []
    for name, raw in TAG.findall(text or ""):
        try:
            out.append((name, json.loads(raw)))
        except json.JSONDecodeError:
            continue
    return out


def tag(name: str, data: dict) -> str:
    return f"<!-- kit:{name} {json.dumps(data, ensure_ascii=False)} -->"


def dump(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


# ------------------------------------------------------------------ STOP

def cmd_stop(_args) -> int:
    path = ROOT / STOP_FILE
    if path.exists():
        print(f"STOP active ({STOP_FILE}): {path.read_text(encoding='utf-8').strip() or '(no text)'}")
        return 3
    print("STOP inactive")
    return 0


# ------------------------------------------------------------------ state validation

def check_limits(limits: dict) -> list[str]:
    errors = []

    def get(path: str):
        node = limits
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                errors.append(f"{LIMITS}: missing key {path}")
                return None
            node = node[key]
        return node

    cap = get("revenue.period_limit")
    if cap is not None and (not isinstance(cap, (int, float)) or cap < 0):
        errors.append(f"{LIMITS}: revenue.period_limit must be a number >= 0 (0 disables the cap)")
    thresholds = get("revenue.alert_thresholds")
    if thresholds is not None and (not isinstance(thresholds, list) or thresholds != sorted(thresholds)
                                   or not all(isinstance(p, (int, float)) and 0 < p <= 1 for p in thresholds)):
        errors.append(f"{LIMITS}: revenue.alert_thresholds must be an ascending list of numbers in (0, 1]")
    for path in ("alerts.max_per_day", "alerts.repeat_silence_h", "tasks.lease_h", "tasks.max_attempts"):
        value = get(path)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            errors.append(f"{LIMITS}: {path} must be an integer >= 1")
    spend = get("spending.without_desk")
    if spend is not None and spend != 0:
        errors.append(f"{LIMITS}: spending.without_desk must be 0 (constitution, rule 4)")
    if get("desk.no_answer") not in (None, "decline"):
        errors.append(f"{LIMITS}: desk.no_answer must be 'decline'")
    routines = get("routines")
    if isinstance(routines, dict):
        for name, r in routines.items():
            if not isinstance(r, dict) or not isinstance(r.get("max_silence_h"), (int, float)):
                errors.append(f"{LIMITS}: routines.{name}.max_silence_h must be a number")
    return errors


def check_ledger(rows: list[dict]) -> list[str]:
    errors, seen = [], set()
    for i, w in enumerate(rows, start=1):
        where = f"{LEDGER} no {w.get('no')}"
        try:
            if w["no"] != str(i):
                errors.append(f"{where}: no should be {i}")
            date.fromisoformat(w["date"])
            amount, rate, base = number(w["amount"]), number(w["rate"], "rate"), number(w["amount_base"], "amount_base")
            if not re.fullmatch(r"[A-Z]{3}", w["currency"]):
                errors.append(f"{where}: currency must be an ISO code, e.g. EUR")
            if (amount * rate).quantize(CENT, ROUND_HALF_UP) != base:
                errors.append(f"{where}: amount_base != amount x rate")
            if w["correction_of"] and (not w["correction_of"].isdigit() or int(w["correction_of"]) >= i):
                errors.append(f"{where}: correction_of must point to an earlier entry")
            if amount < 0 and not w["correction_of"]:
                errors.append(f"{where}: negative amount (refund) requires correction_of")
            key = (w["channel"], w["transaction_id"])
            if not all(key):
                errors.append(f"{where}: channel and transaction_id are required")
            elif key in seen:
                errors.append(f"{where}: duplicate transaction {key}")
            seen.add(key)
        except (ValueError, TypeError, AttributeError, DataError) as e:
            errors.append(f"{where}: {e}")
    return errors


def check_costs(rows: list[dict]) -> list[str]:
    errors = []
    for i, w in enumerate(rows, start=1):
        where = f"{COSTS} no {w.get('no')}"
        try:
            if w["no"] != str(i):
                errors.append(f"{where}: no should be {i}")
            date.fromisoformat(w["date"])
            if number(w["amount_base"], "amount_base") < 0:
                errors.append(f"{where}: a cost cannot be negative")
            if not w["desk_no"].isdigit():
                errors.append(f"{where}: every cost needs the number of the desk item that approved it")
        except (ValueError, TypeError, AttributeError, DataError) as e:
            errors.append(f"{where}: {e}")
    return errors


def check_calibration(rows: list[dict]) -> list[str]:
    errors = []
    for n, w in enumerate(rows, start=2):
        where = f"{CALIBRATION} row {n}"
        try:
            date.fromisoformat(w["date"])
            date.fromisoformat(w["deadline"])
            if not 0 <= number(w["probability"], "probability") <= 1:
                errors.append(f"{where}: probability outside [0, 1]")
            if w["outcome"] not in ("", "0", "1"):
                errors.append(f"{where}: outcome must be empty, 0 or 1")
        except (ValueError, TypeError, AttributeError, DataError) as e:
            errors.append(f"{where}: {e}")
    return errors


def cmd_state(_args) -> int:
    errors = []
    try:
        errors += check_limits(load_limits())
    except DataError as e:
        errors.append(str(e))
    for rel, fields, check in ((LEDGER, LEDGER_FIELDS, check_ledger), (COSTS, COSTS_FIELDS, check_costs),
                               (CALIBRATION, CALIBRATION_FIELDS, check_calibration)):
        try:
            errors += check(read_csv(rel, fields))
        except DataError as e:
            errors.append(str(e))
    if errors:
        print("State CORRUPTED - no external actions until repaired:")
        for e in errors:
            print(f"- {e}")
        return 1
    print("State OK")
    return 0


# ------------------------------------------------------------------ revenue cap (optional)

def period_of(day: date, months: int) -> tuple[int, int]:
    return day.year, (day.month - 1) // months


def revenue_status(day: date) -> dict | None:
    """Revenue in the current period vs revenue.period_limit. None when the cap is disabled."""
    limits = load_limits()
    cap = Decimal(str(limits["revenue"]["period_limit"]))
    if cap == 0:
        return None
    months = int(limits["revenue"].get("period_months", 3))
    period = period_of(day, months)
    try:
        total = sum((number(w["amount_base"]) for w in read_csv(LEDGER, LEDGER_FIELDS)
                     if period_of(date.fromisoformat(w["date"]), months) == period), Decimal("0"))
    except (ValueError, TypeError) as e:
        raise DataError(f"{LEDGER}: corrupted entry ({e}) - run kit.py state check")
    share = total / cap
    crossed = [p for p in limits["revenue"]["alert_thresholds"] if share >= Decimal(str(p))]
    return {
        "period": f"{period[0]}-P{period[1] + 1}",
        "revenue": str(total.quantize(CENT)),
        "limit": str(cap.quantize(CENT)),
        "percent": float((share * 100).quantize(Decimal("0.1"))),
        "threshold": max(crossed) if crossed else None,
        "remaining": str((cap - total).quantize(CENT)),
    }


def cmd_cap(args) -> int:
    day = date.fromisoformat(args.date) if args.date else today()
    dump(revenue_status(day) or {"cap": "disabled"})
    return 0


def cmd_ledger_add(args) -> int:
    rows = read_csv(LEDGER, LEDGER_FIELDS)
    for w in rows:
        if (w["channel"], w["transaction_id"]) == (args.channel, args.transaction_id):
            print(f"Transaction already in the ledger (no {w['no']}) - nothing added.")
            return 0
    day = date.fromisoformat(args.date) if args.date else today()
    currency = args.currency.upper()
    base = load_limits().get("base_currency", "USD")
    if currency == base:
        rate = Decimal("1")
    elif args.rate:
        rate = number(args.rate, "rate")
    else:
        raise DataError(f"currency {currency} differs from base currency {base}: pass --rate "
                        "(take the rate from your accountant's source; the tool never guesses)")
    amount = number(args.amount.replace(",", "."))
    if args.correction_of and not any(w["no"] == args.correction_of for w in rows):
        raise DataError(f"correction_of: no entry {args.correction_of}")
    entry = {"no": str(len(rows) + 1), "date": str(day), "channel": args.channel,
             "transaction_id": args.transaction_id, "description": args.description, "amount": str(amount),
             "currency": currency, "rate": str(rate),
             "amount_base": str((amount * rate).quantize(CENT, ROUND_HALF_UP)),
             "correction_of": args.correction_of or ""}
    errors = check_ledger(rows + [entry])
    if errors:
        raise DataError("; ".join(errors))
    path = ROOT / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        if fresh:
            writer.writeheader()
        writer.writerow(entry)
    dump({"added": entry, "cap": revenue_status(day) or {"cap": "disabled"}})
    return 0


# ------------------------------------------------------------------ calibration

def brier(rows: list[dict]) -> dict:
    """Brier score over resolved forecasts (0 = perfect, 0.25 = always saying 50%)."""
    resolved = [(float(r["probability"]), int(r["outcome"])) for r in rows if r["outcome"] in ("0", "1")]
    if not resolved:
        return {"resolved": 0, "brier": None, "mean_forecast": None, "base_rate": None}
    n = len(resolved)
    return {"resolved": n, "brier": round(sum((p - o) ** 2 for p, o in resolved) / n, 4),
            "mean_forecast": round(sum(p for p, _ in resolved) / n, 4),
            "base_rate": round(sum(o for _, o in resolved) / n, 4)}


def cmd_brier(_args) -> int:
    rows = read_csv(CALIBRATION, CALIBRATION_FIELDS)
    errors = check_calibration(rows)
    if errors:
        raise DataError("; ".join(errors))
    dump(brier(rows))
    return 0


# ------------------------------------------------------------------ tasks: leases, intents, results

def cmd_lease(args) -> int:
    hours = args.hours or load_limits()["tasks"]["lease_h"]
    until = iso(now_utc() + timedelta(hours=hours))
    print(f"🔒 Claimed by {args.shift}, lease until {until} (attempt {args.attempt})")
    print(tag("lease", {"shift": args.shift, "until": until, "attempt": args.attempt}))
    return 0


def cmd_intent(args) -> int:
    print(f"📝 Intent `{args.id}`: {args.description}")
    print(tag("intent", {"id": args.id, "description": args.description, "time": iso(now_utc())}))
    return 0


def cmd_result(args) -> int:
    icon = "✅" if args.status == "ok" else "❌"
    print(f"{icon} Result `{args.id}`: {args.status}" + (f" - {args.evidence}" if args.evidence else ""))
    print(tag("result", {"id": args.id, "status": args.status, "evidence": args.evidence or "",
                         "time": iso(now_utc())}))
    return 0


def assess_task(comments: list, now: datetime, max_attempts: int) -> dict:
    leases, intents, results = [], {}, set()
    for c in comments:
        body = c.get("body", "") if isinstance(c, dict) else str(c)
        for name, data in tags(body):
            if name == "lease":
                leases.append(data)
            elif name == "intent":
                intents[data.get("id")] = data.get("description", "")
            elif name == "result":
                results.add(data.get("id"))
    out = {"attempts": len(leases), "next_attempt": len(leases) + 1,
           "unfinished_intents": [{"id": i, "description": d} for i, d in intents.items() if i not in results]}
    if not leases:
        return out | {"lease_until": None, "state": "none", "action": "return_to_queue"}
    until = parse_time(leases[-1]["until"])
    if until > now:
        return out | {"lease_until": iso(until), "state": "active", "action": "leave"}
    action = "block" if len(leases) >= max_attempts else "return_to_queue"
    return out | {"lease_until": iso(until), "state": "expired", "action": action}


def cmd_tasks_assess(args) -> int:
    """Input: JSON list of {"number": N, "comments": [text | {"body": text}, ...]}."""
    tasks = json.loads(Path(args.file).read_text(encoding="utf-8"))
    max_attempts = load_limits()["tasks"]["max_attempts"]
    now = parse_time(args.now) if args.now else now_utc()
    dump([{"number": t["number"]} | assess_task(t.get("comments", []), now, max_attempts) for t in tasks])
    return 0


# ------------------------------------------------------------------ pulse

def pulse_body(routine: str, status: str, description: str, shift: str | None) -> str:
    t = now_utc()
    data = {"routine": routine, "status": status, "time": iso(t), "shift": shift or "", "description": description}
    lines = [tag("pulse", data), f"### Pulse {routine}: {PULSE_ICONS[status]} {status}", "",
             f"- time: {iso(t)}"]
    if shift:
        lines.append(f"- shift: {shift}")
    lines.append(f"- description: {description}")
    return "\n".join(lines)


def cmd_pulse(args) -> int:
    print(pulse_body(args.routine, args.status, args.description, args.shift))
    return 0


# ------------------------------------------------------------------ desk

def check_desk(text: str, day: date) -> list[str]:
    problems = []
    lines = [l for l in text.splitlines() if l.strip()]
    m = DESK_TITLE.match(lines[0]) if lines else None
    if not m:
        problems.append("first line must read: # [DESK] <action> — <amount> — due YYYY-MM-DD")
    elif date.fromisoformat(m.group(1)) < day:
        problems.append(f"due date {m.group(1)} has passed")
    if not re.search(r"\*\*Urgency:\*\*\s*(normal|urgent)", text):
        problems.append("missing line **Urgency:** normal|urgent")
    heads = list(re.finditer(r"^## (.+)$", text, re.M))
    bodies = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        bodies[h.group(1).strip()] = text[h.end():end].strip()
    for name in DESK_SECTIONS:
        if name not in bodies:
            problems.append(f'missing section "{name}"')
        elif not bodies[name]:
            problems.append(f'section "{name}" is empty')
    for inner in sorted(set(PLACEHOLDER.findall(text))):
        if not HTML_TAG.match(inner.strip()):
            problems.append(f"unfilled template field: <{inner}>")
    return problems


def cmd_desk_check(args) -> int:
    problems = check_desk(Path(args.file).read_text(encoding="utf-8"), today())
    if problems:
        print("Item INCOMPLETE - do not publish:")
        for p in problems:
            print(f"- {p}")
        return 1
    print("Item complete")
    return 0


# ------------------------------------------------------------------ guardian

def assess_guardian(pulses: list[dict], constitution_commits: list[dict], limits: dict,
                    now: datetime, stop: bool, cap: dict | None) -> dict:
    """Pure assessment for the guardian (GitHub Actions). Returns alerts and warnings."""
    alerts, warnings = [], []
    owner = limits.get("owner", {}).get("github")

    # 1. constitution/: every commit before the owner's latest commit must be by the owner.
    authors = [((c.get("author") or {}).get("login"), c.get("sha", "")[:7]) for c in constitution_commits]
    owner_idx = [i for i, (login, _) in enumerate(authors) if login == owner]
    if not authors:
        warnings.append("No history for constitution/ - integrity not checked")
    elif not owner_idx:
        warnings.append("Constitution not approved: no commit by the owner in constitution/")
    else:
        foreign = [sha for login, sha in authors[:max(owner_idx)] if login != owner]
        if foreign:
            alerts.append({"code": "SECURITY", "title": "constitution/ changed without the owner",
                           "body": f"Commits not by {owner} after approval: {', '.join(foreign)}. "
                                   "Agents may not change constitution/. Review and revert."})

    if stop:
        warnings.append("STOP active - skipping pulse and cap checks")
        return {"alerts": alerts, "warnings": warnings, "stop": True}

    # 2. Routine pulses.
    latest = {}
    for issue in pulses:
        for name, data in tags(issue.get("body", "")):
            if name != "pulse" or not data.get("routine"):
                continue
            try:
                t = parse_time(str(data.get("time")))
            except ValueError:
                warnings.append(f"{issue.get('title', 'pulse')}: invalid time in pulse")
                continue
            prev = latest.get(data["routine"])
            if prev is None or t > parse_time(prev["time"]):
                latest[data["routine"]] = data
    config = limits.get("routines", {})
    dead = []
    for routine, data in sorted(latest.items()):
        if data.get("status") in ("disabled", "stop") or routine not in config:
            continue
        age_h = (now - parse_time(data["time"])).total_seconds() / 3600
        rules = config[routine]
        if data.get("status") == "in-progress" and age_h > rules.get("max_shift_h", 6):
            warnings.append(f"{routine}: shift in progress for {age_h:.1f} h - probably interrupted")
        if age_h > rules["max_silence_h"]:
            dead.append(routine)
            alert_after = rules.get("alert_after_h")
            if alert_after is not None and age_h > alert_after:
                alerts.append({"code": "OUTAGE", "title": f"Routine {routine} silent for {age_h:.0f} h",
                               "body": f"Last pulse {routine}: {data['time']} ({data.get('status')}). "
                                       "Check the Routines list and your subscription usage limit."})
            else:
                warnings.append(f"{routine}: no pulse for {age_h:.1f} h (limit {rules['max_silence_h']} h)")
    active = [r for r, d in latest.items() if d.get("status") not in ("disabled", "stop") and r in config]
    if len(active) > 1 and set(active) <= set(dead):
        alerts.append({"code": "OUTAGE", "title": "All routines silent",
                       "body": f"No pulse from: {', '.join(sorted(active))}. The business is standing still."})

    # 3. Revenue cap (optional).
    if cap and cap.get("threshold") is not None:
        if cap["threshold"] >= 0.95:
            alerts.append({"code": "CAP", "title": f"Revenue {cap['period']}: {cap['percent']}% of cap",
                           "body": f"Revenue {cap['revenue']} of {cap['limit']}. "
                                   "Decision needed: change legal form or pause sales."})
        else:
            warnings.append(f"Revenue cap {cap['period']}: {cap['percent']}%")
    return {"alerts": alerts, "warnings": warnings, "stop": False}


def cmd_guardian(args) -> int:
    limits = load_limits()
    pulses = json.loads(Path(args.pulses).read_text(encoding="utf-8")) if args.pulses else []
    commits = json.loads(Path(args.constitution_commits).read_text(encoding="utf-8")) if args.constitution_commits else []
    now = parse_time(args.now) if args.now else now_utc()
    try:
        cap = revenue_status(now.astimezone(tz(limits)).date())
    except (DataError, KeyError, ValueError) as e:
        cap = None
        print(f"warning: revenue cap not computed ({e})", file=sys.stderr)
    dump(assess_guardian(pulses, commits, limits, now, (ROOT / STOP_FILE).exists(), cap))
    return 0


# ------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kit", description="Agent Business Kit helper")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("stop", help="is the STOP switch active (exit 3)").set_defaults(f=cmd_stop)
    sub.add_parser("state", help="validate state files").add_subparsers(dest="sub", required=True) \
        .add_parser("check").set_defaults(f=cmd_state)

    cap = sub.add_parser("cap", help="revenue in the current period vs the optional cap")
    cap.add_argument("--date")
    cap.set_defaults(f=cmd_cap)

    led = sub.add_parser("ledger", help="sales ledger").add_subparsers(dest="sub", required=True)
    add = led.add_parser("add")
    add.add_argument("--date")
    add.add_argument("--channel", required=True)
    add.add_argument("--transaction-id", required=True)
    add.add_argument("--description", required=True)
    add.add_argument("--amount", required=True)
    add.add_argument("--currency", default="USD")
    add.add_argument("--rate", help="rate to the base currency (required when currencies differ)")
    add.add_argument("--correction-of")
    add.set_defaults(f=cmd_ledger_add)

    sub.add_parser("brier", help="Brier score of resolved forecasts").set_defaults(f=cmd_brier)

    ls = sub.add_parser("lease", help="comment text for claiming a task")
    ls.add_argument("--shift", required=True)
    ls.add_argument("--hours", type=int)
    ls.add_argument("--attempt", type=int, default=1)
    ls.set_defaults(f=cmd_lease)

    it = sub.add_parser("intent", help="record an intent before an external action")
    it.add_argument("--id", required=True)
    it.add_argument("--description", required=True)
    it.set_defaults(f=cmd_intent)

    rs = sub.add_parser("result", help="record the result of an external action")
    rs.add_argument("--id", required=True)
    rs.add_argument("--status", choices=["ok", "error"], required=True)
    rs.add_argument("--evidence")
    rs.set_defaults(f=cmd_result)

    tk = sub.add_parser("tasks", help="lease assessment").add_subparsers(dest="sub", required=True)
    ta = tk.add_parser("assess")
    ta.add_argument("file")
    ta.add_argument("--now")
    ta.set_defaults(f=cmd_tasks_assess)

    pu = sub.add_parser("pulse", help="body of a routine's pulse issue")
    pu.add_argument("--routine", required=True)
    pu.add_argument("--status", choices=list(PULSE_ICONS), required=True)
    pu.add_argument("--description", required=True)
    pu.add_argument("--shift")
    pu.set_defaults(f=cmd_pulse)

    de = sub.add_parser("desk", help="desk item completeness").add_subparsers(dest="sub", required=True)
    dc = de.add_parser("check")
    dc.add_argument("file")
    dc.set_defaults(f=cmd_desk_check)

    g = sub.add_parser("guardian", help="assessment for the guardian")
    g.add_argument("--pulses")
    g.add_argument("--constitution-commits")
    g.add_argument("--now")
    g.set_defaults(f=cmd_guardian)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.f(args)
    except ConfigError as e:
        print(f"configuration error: {e}", file=sys.stderr)
        return 2
    except DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
