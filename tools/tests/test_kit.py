import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import alarm  # noqa: E402
import guardian  # noqa: E402
import kit  # noqa: E402

LIMITS = json.loads((TOOLS.parent / "constitution/limits.json").read_text(encoding="utf-8"))
LIMITS["owner"] = {"github": "owner"}
LIMITS["revenue"]["period_limit"] = 1000
OPERATIONS = LIMITS["routines"]["operations"]
SILENT_H = OPERATIONS["alert_after_h"] + 1  # operations silent long enough for an OUTAGE alert
QUIET_H = OPERATIONS["max_silence_h"] + 1  # past the warning threshold, not yet an outage
ALERT_BUDGET = LIMITS["alerts"]["max_per_day"]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = kit.main(argv)
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "constitution").mkdir()
        self.write_limits(LIMITS)
        p = mock.patch.object(kit, "ROOT", self.root)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict("os.environ", {"KIT_NOW": "2026-05-10T12:00:00Z"})
        p.start()
        self.addCleanup(p.stop)

    def write_limits(self, data):
        (self.root / kit.LIMITS).write_text(json.dumps(data), encoding="utf-8")


class TestStopAndState(Base):
    def test_stop(self):
        self.assertEqual(run(["stop"])[0], 0)
        (self.root / kit.STOP_FILE).write_text("maintenance", encoding="utf-8")
        code, out, _ = run(["stop"])
        self.assertEqual(code, 3)
        self.assertIn("maintenance", out)

    def test_state_ok_and_shipped_limits_valid(self):
        self.assertEqual(run(["state", "check"])[0], 0)
        self.assertEqual(kit.check_limits(json.loads((TOOLS.parent / "constitution/limits.json").read_text())), [])

    def test_spending_must_be_zero_and_desk_must_decline(self):
        bad = json.loads(json.dumps(LIMITS))
        bad["spending"]["without_desk"] = 5
        bad["desk"]["no_answer"] = "approve"
        bad["routines"]["operations"]["max_silence_h"] = "x"
        errors = kit.check_limits(bad)
        self.assertEqual(len(errors), 3)

    def test_missing_limits_is_config_error(self):
        (self.root / kit.LIMITS).unlink()
        self.assertEqual(run(["state", "check"])[0], 1)
        self.assertEqual(run(["cap"])[0], 2)

    def test_timezone_typo_fails_state_check(self):
        bad = dict(LIMITS, timezone="Europe/Berlinn")
        self.assertTrue(any("timezone" in e for e in kit.check_limits(bad)))
        self.assertEqual(kit.tz(bad).utcoffset(datetime(2026, 1, 1)), timedelta(0))  # readers fall back to UTC
        self.write_limits(bad)
        self.assertEqual(run(["state", "check"])[0], 1)
        self.assertEqual(kit.check_limits(dict(LIMITS, timezone="Europe/Berlin")), [])
        self.assertTrue(any("timezone" in e for e in kit.check_limits(dict(LIMITS, timezone=7))))

    def test_tz_does_not_hide_configuration_errors(self):
        (self.root / kit.LIMITS).unlink()
        with self.assertRaises(kit.ConfigError):
            kit.tz()
        with self.assertRaises(kit.ConfigError):
            kit.tz({"timezone": ["UTC"]})

    def test_period_months_must_divide_the_year(self):
        for months in (1, 2, 3, 4, 6, 12):
            self.assertEqual(kit.check_limits(json.loads(json.dumps(LIMITS)) | {
                "revenue": dict(LIMITS["revenue"], period_months=months)}), [], months)
        for months in (5, 7, 0, 3.0, True, "3"):
            bad = json.loads(json.dumps(LIMITS))
            bad["revenue"]["period_months"] = months
            self.assertTrue(any("period_months" in e for e in kit.check_limits(bad)), months)
        bad["revenue"]["period_months"] = 5
        self.write_limits(bad)
        self.assertEqual(run(["cap"])[0], 2)

    def test_owner_login_required(self):
        for owner in ({"github": ""}, {"github": "  "}, {}, None, {"github": None}):
            bad = dict(LIMITS, owner=owner)
            self.assertTrue(any("owner.github" in e for e in kit.check_limits(bad)), owner)
            with self.assertRaises(kit.ConfigError):
                kit.assess_guardian([], [{"sha": "a" * 40, "author": None}], bad, kit.now_utc(), False, None)

    def test_corrupt_ledger_detected(self):
        (self.root / "finance").mkdir()
        (self.root / kit.LEDGER).write_text("wrong,header\n1,2\n", encoding="utf-8")
        code, out, _ = run(["state", "check"])
        self.assertEqual(code, 1)
        self.assertIn("header", out)


class TestLedgerAndCap(Base):
    def add(self, *extra, tid="t1", amount="100"):
        return run(["ledger", "add", "--channel", "shop", "--transaction-id", tid, "--description", "sale",
                    "--amount", amount, *extra])

    def test_add_and_idempotent(self):
        self.assertEqual(self.add()[0], 0)
        code, out, _ = self.add()
        self.assertIn("already in the ledger", out)
        self.assertEqual(len(kit.read_csv(kit.LEDGER, kit.LEDGER_FIELDS)), 1)
        self.assertEqual(run(["state", "check"])[0], 0)

    def test_foreign_currency_needs_rate(self):
        code, _, err = self.add("--currency", "EUR")
        self.assertEqual(code, 1)
        self.assertIn("--rate", err)
        self.assertEqual(self.add("--currency", "EUR", "--rate", "1.1", tid="t2")[0], 0)
        self.assertEqual(kit.read_csv(kit.LEDGER, kit.LEDGER_FIELDS)[0]["amount_base"], "110.00")

    def test_rate_must_be_positive(self):
        for rate in ("0", "-1.1"):
            code, _, err = self.add("--currency", "EUR", "--rate", rate)
            self.assertEqual(code, 1)
            self.assertIn("rate", err)
        self.assertEqual(kit.read_csv(kit.LEDGER, kit.LEDGER_FIELDS), [])
        row = {"no": "1", "date": "2026-05-10", "channel": "shop", "transaction_id": "t1", "description": "x",
               "amount": "10", "currency": "EUR", "rate": "0", "amount_base": "0.00", "correction_of": ""}
        self.assertIn("no 1: rate must be greater than 0", " | ".join(kit.check_ledger([row])))

    def test_formula_description_is_neutralised(self):
        for i, text in enumerate(("=HYPERLINK(1)", "+1", "-1", "@SUM(A1)")):
            self.assertEqual(run(["ledger", "add", "--channel", "shop", "--transaction-id", f"f{i}",
                                  "--description", text, "--amount", "5"])[0], 0)
        self.add(tid="plain")
        descriptions = [w["description"] for w in kit.read_csv(kit.LEDGER, kit.LEDGER_FIELDS)]
        self.assertEqual(descriptions, ["'=HYPERLINK(1)", "'+1", "'-1", "'@SUM(A1)", "sale"])

    def test_invalid_dates_are_validation_errors(self):
        code, _, err = run(["cap", "--date", "2026-13-01"])
        self.assertEqual(code, 1)
        self.assertIn("invalid date", err)
        self.assertEqual(self.add("--date", "yesterday")[0], 1)

    def test_negative_requires_correction(self):
        self.add()
        self.assertEqual(self.add(tid="r1", amount="-10")[0], 1)
        self.assertEqual(self.add("--correction-of", "1", tid="r1", amount="-10")[0], 0)

    def test_cap_thresholds(self):
        self.add(amount="820")
        status = kit.revenue_status(date(2026, 5, 10))
        self.assertEqual((status["percent"], status["threshold"], status["remaining"]), (82.0, 0.8, "180.00"))
        self.assertEqual(kit.revenue_status(date(2026, 8, 1))["revenue"], "0.00")  # next period

    def test_cap_period_does_not_span_years(self):
        limits = json.loads(json.dumps(LIMITS))
        limits["revenue"]["period_months"] = 6
        self.write_limits(limits)
        self.add("--date", "2025-12-20", amount="300")
        self.assertEqual(kit.revenue_status(date(2025, 12, 31))["period"], "2025-P2")
        status = kit.revenue_status(date(2026, 1, 2))
        self.assertEqual((status["period"], status["revenue"]), ("2026-P1", "0.00"))

    def test_cap_disabled(self):
        off = json.loads(json.dumps(LIMITS))
        off["revenue"]["period_limit"] = 0
        self.write_limits(off)
        self.assertIsNone(kit.revenue_status(date(2026, 5, 10)))
        self.assertIn("disabled", run(["cap"])[1])


class TestBrier(Base):
    def test_brier(self):
        rows = [{"probability": "0.8", "outcome": "1"}, {"probability": "0.4", "outcome": "0"},
                {"probability": "0.5", "outcome": ""}]
        self.assertEqual(kit.brier(rows)["brier"], 0.1)
        self.assertEqual(kit.brier(rows)["resolved"], 2)
        self.assertIsNone(kit.brier([])["brier"])

    def test_calibration_validation(self):
        bad = [{"date": "2026-01-01", "deadline": "2026-02-01", "probability": "1.5", "outcome": "2"}]
        self.assertEqual(len(kit.check_calibration(bad)), 2)


class TestTasks(Base):
    def lease(self, hours, attempt=1):
        until = kit.iso(kit.now_utc() + timedelta(hours=hours))
        return kit.tag("lease", {"shift": "operations-1", "until": until, "attempt": attempt})

    def test_lease_command_roundtrip(self):
        code, out, _ = run(["lease", "--shift", "operations-1"])
        self.assertEqual(code, 0)
        self.assertIn(kit.iso(kit.now_utc() + timedelta(hours=LIMITS["tasks"]["lease_h"])), out)
        self.assertEqual(kit.tags(out)[0][0], "lease")

    def test_active_expired_blocked(self):
        now, cap = kit.now_utc(), 3
        self.assertEqual(kit.assess_task([self.lease(2)], now, cap)["action"], "leave")
        self.assertEqual(kit.assess_task([self.lease(-1)], now, cap)["action"], "return_to_queue")
        self.assertEqual(kit.assess_task([self.lease(-1)] * 3, now, cap)["action"], "block")
        self.assertEqual(kit.assess_task([], now, cap)["action"], "return_to_queue")

    def test_unfinished_intents(self):
        comments = [{"body": kit.tag("intent", {"id": "pub-1", "description": "publish"})},
                    {"body": kit.tag("intent", {"id": "pub-2", "description": "tweet"})},
                    {"body": kit.tag("result", {"id": "pub-1", "status": "ok"})}]
        result = kit.assess_task(comments, kit.now_utc(), 3)
        self.assertEqual([i["id"] for i in result["unfinished_intents"]], ["pub-2"])

    def test_tags_ignore_garbage(self):
        self.assertEqual(kit.tags("<!-- kit:lease {not json} --> text"), [])

    def test_assess_cli(self):
        f = self.root / "tasks.json"
        f.write_text(json.dumps([{"number": 7, "comments": [self.lease(-1)]}]), encoding="utf-8")
        code, out, _ = run(["tasks", "assess", str(f)])
        self.assertEqual(json.loads(out)[0]["action"], "return_to_queue")

    def test_assess_cli_bad_input(self):
        f = self.root / "tasks.json"
        self.assertEqual(run(["tasks", "assess", str(self.root / "missing.json")])[0], 1)
        for content in ("{not json", json.dumps({"number": 1}), json.dumps([{"comments": []}]),
                        json.dumps([{"number": 1, "comments": [kit.tag("lease", {"until": "soon"})]}])):
            f.write_text(content, encoding="utf-8")
            code, _, err = run(["tasks", "assess", str(f)])
            self.assertEqual(code, 1, content)
            self.assertIn("tasks.json", err)

    def test_intent_result_pulse(self):
        self.assertIn("kit:intent", run(["intent", "--id", "x", "--description", "d"])[1])
        self.assertIn("❌", run(["result", "--id", "x", "--status", "error"])[1])
        out = run(["pulse", "--routine", "operations", "--status", "ok", "--description", "fine"])[1]
        self.assertEqual(kit.tags(out)[0][1]["routine"], "operations")


GOOD_DESK = """# [DESK] Register a domain — 12 USD — due 2026-05-20

**Urgency:** normal    **Department:** strategy

## What exactly you need to do
1. Open <https://example.com/register> and buy `example-shop.test`.
## Why
Needed for the shop landing page.
## Cost and return
12 USD once.
## Risks and mitigation
- Name taken -> alternatives listed.
## Alternatives considered
- Subdomain - weaker brand.
## Recommendation
YES, confidence high.
## If you decline or do not answer
We keep the free subdomain.
## Attachments
none
"""


class TestDesk(Base):
    def test_complete(self):
        self.assertEqual(kit.check_desk(GOOD_DESK, date(2026, 5, 10)), [])

    def test_problems(self):
        text = GOOD_DESK.replace("## Why\nNeeded for the shop landing page.\n", "").replace("12 USD once.", "<amount>")
        problems = kit.check_desk(text, date(2026, 6, 1))
        joined = " | ".join(problems)
        self.assertIn("has passed", joined)
        self.assertIn('missing section "Why"', joined)
        self.assertIn("<amount>", joined)

    def test_unchanged_urgency_template_rejected(self):
        for line in ("**Urgency:** normal | urgent", "**Urgency:** normal|urgent", "**Urgency:** <normal|urgent>"):
            text = GOOD_DESK.replace("**Urgency:** normal", line)
            self.assertIn("missing line **Urgency:** normal|urgent", kit.check_desk(text, date(2026, 5, 10)), line)
        self.assertEqual(kit.check_desk(GOOD_DESK.replace("normal", "urgent", 1), date(2026, 5, 10)), [])
        template = (TOOLS.parent / "processes/DESK.md").read_text(encoding="utf-8")
        self.assertIn("**Urgency:** <normal|urgent>", template)
        self.assertIn("unfilled template field: <normal|urgent>", kit.check_desk(template, date(2026, 5, 10)))

    def test_cli_missing_file(self):
        code, _, err = run(["desk", "check", str(self.root / "missing.md")])
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)

    def test_cli(self):
        f = self.root / "item.md"
        f.write_text(GOOD_DESK, encoding="utf-8")
        self.assertEqual(run(["desk", "check", str(f)])[0], 0)
        f.write_text("# not a desk item", encoding="utf-8")
        self.assertEqual(run(["desk", "check", str(f)])[0], 1)


def pulse_issue(routine, hours_ago, status="ok", **extra):
    t = kit.now_utc() - timedelta(hours=hours_ago)
    return {"title": f"Pulse: {routine}",
            "body": kit.tag("pulse", {"routine": routine, "status": status, "time": kit.iso(t)}), **extra}


def commit(login, letter):
    return {"sha": letter * 40, "author": {"login": login}}


class TestGuardian(Base):
    def assess(self, pulses, commits=None, stop=False, cap=None):
        return kit.assess_guardian(pulses, commits if commits is not None else [{"sha": "a" * 40, "author": {"login": "owner"}}],
                                   LIMITS, kit.now_utc(), stop, cap)

    def test_healthy(self):
        r = self.assess([pulse_issue("operations", 2), pulse_issue("strategy", 5), pulse_issue("finance", 5)])
        self.assertEqual((r["alerts"], r["warnings"]), ([], []))

    def test_configured_routine_without_pulse_is_reported(self):
        r = self.assess([pulse_issue("operations", 2), pulse_issue("strategy", 5)])
        self.assertEqual((r["alerts"], r["warnings"]), ([], ["no pulse issue for finance"]))
        # Fresh install: nothing reports yet, so only warnings (the guardian's own pulse is not expected).
        r = self.assess([])
        self.assertEqual(r["alerts"], [])
        self.assertEqual(sorted(r["warnings"]), ["no pulse issue for finance", "no pulse issue for operations",
                                                 "no pulse issue for strategy"])

    def test_missing_operational_routine_alerts_once_business_runs(self):
        def created(hours_ago):
            return kit.iso(kit.now_utc() - timedelta(hours=hours_ago))
        # Strategy has reported for less than the operations alert_after_h: still a warning.
        recent = created(OPERATIONS["alert_after_h"] - 1)
        r = self.assess([pulse_issue("strategy", 1, createdAt=recent), pulse_issue("finance", 1)])
        self.assertEqual(r["alerts"], [])
        self.assertIn("no pulse issue for operations", r["warnings"])
        # Strategy has reported for longer than that and operations never did: outage.
        r = self.assess([pulse_issue("strategy", 1, createdAt=created(SILENT_H)), pulse_issue("finance", 1)])
        self.assertEqual([(a["code"], a["title"]) for a in r["alerts"]], [("OUTAGE", "Routine operations silent")])
        # Strategy and finance have no alert_after_h, so their absence stays a warning however long operations
        # runs.
        r = self.assess([pulse_issue("operations", 1, createdAt=created(100))])
        self.assertEqual(r["alerts"], [])
        # A disabled routine is not evidence that the business is running.
        r = self.assess([pulse_issue("strategy", 1, "disabled", createdAt=created(100))])
        self.assertEqual(r["alerts"], [])

    def test_guardian_pulse_is_not_an_anchor_for_missing_routine(self):
        old = kit.iso(kit.now_utc() - timedelta(hours=100))
        r = self.assess([pulse_issue("GUARDIAN", 1, createdAt=old)])
        self.assertEqual(r["alerts"], [])
        self.assertIn("no pulse issue for operations", r["warnings"])

    def test_closed_pulse_issue_still_checked(self):
        r = self.assess([pulse_issue("operations", SILENT_H, state="CLOSED", number=7), pulse_issue("strategy", 2),
                         pulse_issue("finance", 2)])
        self.assertEqual([a["title"] for a in r["alerts"]], ["Routine operations silent"])
        self.assertIn("operations: pulse issue #%d is closed - reopen it" % 7, r["warnings"])
        # A closed old issue next to an open one is not worth a warning.
        r = self.assess([pulse_issue("operations", 30, state="CLOSED", number=7), pulse_issue("operations", 1, state="OPEN"),
                         pulse_issue("strategy", 2), pulse_issue("finance", 2)])
        self.assertEqual((r["alerts"], r["warnings"]), ([], []))

    def test_operations_outage_alerts_after_threshold(self):
        r = self.assess([pulse_issue("operations", SILENT_H), pulse_issue("strategy", 2)])
        self.assertEqual([a["code"] for a in r["alerts"]], ["OUTAGE"])
        r = self.assess([pulse_issue("operations", QUIET_H), pulse_issue("strategy", 2)])
        self.assertEqual(r["alerts"], [])
        self.assertTrue(any("operations" in w for w in r["warnings"]))

    def test_all_silent(self):
        r = self.assess([pulse_issue("operations", 40), pulse_issue("strategy", 40)])
        self.assertIn("All routines silent", [a["title"] for a in r["alerts"]])
        # The guardian's own pulse is always fresh; it must not mask the outage.
        r = self.assess([pulse_issue("operations", 40), pulse_issue("strategy", 40), pulse_issue("GUARDIAN", 1)])
        self.assertIn("All routines silent", [a["title"] for a in r["alerts"]])
        r = self.assess([pulse_issue("operations", 40), pulse_issue("strategy", 2), pulse_issue("GUARDIAN", 1)])
        self.assertNotIn("All routines silent", [a["title"] for a in r["alerts"]])

    def test_outage_title_is_stable(self):
        first = self.assess([pulse_issue("operations", SILENT_H)])["alerts"][0]
        later = kit.assess_guardian([pulse_issue("operations", SILENT_H)], [], LIMITS,
                                    kit.now_utc() + timedelta(hours=1), False, None)
        self.assertEqual(first["title"], "Routine operations silent")
        self.assertEqual(later["alerts"][0]["title"], first["title"])
        self.assertIn(f"{SILENT_H + 1} h", later["alerts"][0]["body"])

    def test_stuck_shift_warning(self):
        r = self.assess([pulse_issue("operations", OPERATIONS["max_shift_h"] + 1, "in-progress")])
        self.assertTrue(any("interrupted" in w for w in r["warnings"]))

    def test_constitution_tampering(self):
        # The GitHub API lists newest first. Agent commits before the owner's approval are tolerated.
        commits = [{"sha": "b" * 40, "author": {"login": "owner"}}, {"sha": "c" * 40, "author": {"login": "agent"}}]
        self.assertEqual(self.assess([], commits)["alerts"], [])
        commits = [{"sha": "c" * 40, "author": {"login": "agent"}}, {"sha": "b" * 40, "author": {"login": "owner"}}]
        self.assertEqual(self.assess([], commits)["alerts"][0]["code"], "SECURITY")

    def test_owner_commit_after_review_clears_security_alert(self):
        # Chronological owner -> agent -> owner; listed newest first. The owner's latest commit approves
        # the state, so the older agent commit no longer alerts.
        commits = [commit("owner", "d"), commit("agent", "c"), commit("owner", "b")]
        self.assertEqual(self.assess([], commits)["alerts"], [])
        # An agent commit after the owner's latest one alerts, and only that commit is named.
        commits = [commit("agent", "e"), commit("owner", "d"), commit("agent", "c"), commit("owner", "b")]
        alerts = self.assess([], commits)["alerts"]
        self.assertEqual([a["code"] for a in alerts], ["SECURITY"])
        self.assertIn("eeeeeee", alerts[0]["body"])
        self.assertNotIn("ccccccc", alerts[0]["body"])
        self.assertIn("alert clears once the owner", alerts[0]["body"])

    def test_truncated_history_without_owner_commit_alerts(self):
        commits = [commit("agent", "c")] * 3
        r = kit.assess_guardian([], commits, LIMITS, kit.now_utc(), False, None, history_complete=False)
        self.assertEqual([a["code"] for a in r["alerts"]], ["SECURITY"])
        r = kit.assess_guardian([], commits, LIMITS, kit.now_utc(), False, None, history_complete=True)
        self.assertEqual(r["alerts"], [])

    def test_no_owner_commit_and_no_history(self):
        self.assertIn("not approved", self.assess([], [{"sha": "a" * 40, "author": {"login": "x"}}])["warnings"][0])
        empty = kit.assess_guardian([], [], LIMITS, kit.now_utc(), False, None)
        self.assertIn("No history", empty["warnings"][0])

    def test_stop_skips_pulse_checks(self):
        r = self.assess([pulse_issue("operations", 99)], stop=True)
        self.assertTrue(r["stop"])
        self.assertEqual(r["alerts"], [])

    def test_cap_alert(self):
        highest, lower = LIMITS["revenue"]["alert_thresholds"][-1], LIMITS["revenue"]["alert_thresholds"][-2]
        cap = {"period": "2026-P2", "revenue": "960", "limit": "1000", "percent": 96.0, "threshold": highest}
        self.assertEqual(self.assess([], cap=cap)["alerts"][0]["code"], "CAP")
        first = self.assess([], cap=cap)["alerts"][0]
        cap.update(revenue="990", percent=99.0)
        later = self.assess([], cap=cap)["alerts"][0]
        self.assertEqual((first["title"], later["title"]), ("Revenue cap 2026-P2 reached",) * 2)
        self.assertIn("99.0%", later["body"])
        cap.update(threshold=lower, percent=lower * 100 + 1)
        self.assertEqual(self.assess([], cap=cap)["alerts"], [])

    def test_cap_alert_uses_highest_configured_threshold(self):
        limits = json.loads(json.dumps(LIMITS))
        limits["revenue"]["alert_thresholds"] = [0.75, 0.85]
        cap = {"period": "2026-P2", "revenue": "850", "limit": "1000", "percent": 85.0, "threshold": 0.85}
        r = kit.assess_guardian([], [commit("owner", "a")], limits, kit.now_utc(), False, cap)
        self.assertEqual([a["code"] for a in r["alerts"]], ["CAP"])
        cap.update(threshold=0.75, percent=80.0)
        r = kit.assess_guardian([], [commit("owner", "a")], limits, kit.now_utc(), False, cap)
        self.assertEqual(r["alerts"], [])
        self.assertIn("Revenue cap 2026-P2: 80.0%", r["warnings"])


class FakeDiscord:
    """Replaces alarm.http with an in-memory channel."""

    def __init__(self):
        self.sent, self.reactions, self.history = [], [], []

    def __call__(self, cfg, method, url, data=None, bot=True):
        if method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            start = 0
            if "before" in query:
                start = next(i for i, m in enumerate(self.history) if m["id"] == query["before"][0]) + 1
            return self.history[start:start + int(query.get("limit", ["50"])[0])]
        if method == "POST":
            self.sent.append(data["content"])
            self.history.insert(0, {"id": str(len(self.sent)), "content": data["content"], "author": {"bot": True},
                                    "timestamp": kit.iso(kit.now_utc())})
            return {}
        self.reactions.append(url)
        return None


CFG = {"token": "t", "channel": "1", "owner": "42", "webhook": "", "proxy": False, "api": "http://x"}


class TestAlarm(Base):
    def setUp(self):
        super().setUp()
        self.fake = FakeDiscord()
        p = mock.patch.object(alarm, "http", self.fake)
        p.start()
        self.addCleanup(p.stop)

    def send(self, code="OUTAGE", title="t"):
        return alarm.alarm(CFG, code, title, "body", "", "", LIMITS)

    def test_send_and_dedupe(self):
        self.assertEqual(self.send()[0], 0)
        self.assertIn("<@42>", self.fake.sent[0])
        self.assertIn("duplicate", self.send()[1])
        self.assertEqual(len(self.fake.sent), 1)

    def test_daily_budget_and_security_exempt(self):
        for i in range(ALERT_BUDGET):
            self.assertEqual(self.send(title=f"a{i}")[0], 0)
        self.assertEqual(self.send(title="over budget")[0], 4)
        self.assertEqual(self.send("SECURITY", "leak")[0], 0)

    def test_no_config_is_plan_b(self):
        empty = dict(CFG, token="", channel="")
        self.assertEqual(alarm.alarm(empty, "LEGAL", "t", "b", "", "", LIMITS)[0], 2)

    def test_desk_once_a_day(self):
        self.assertEqual(alarm.desk(CFG, "1 item", LIMITS)[1], "desk notice sent")
        self.assertIn("already sent", alarm.desk(CFG, "2 items", LIMITS)[1])

    def test_owner_commands_only(self):
        self.fake.history = [
            {"id": "3", "content": "!yes 123", "author": {"id": "42"}, "timestamp": "2026-05-10T11:00:00Z"},
            {"id": "2", "content": "!start", "author": {"id": "99"}, "timestamp": "2026-05-10T10:30:00Z"},
            {"id": "1", "content": "!stop", "author": {"id": "42"}, "timestamp": "2026-05-10T10:00:00Z"}]
        result = alarm.commands(CFG)
        self.assertTrue(result["stop"])  # the stranger's !start is ignored
        self.assertEqual([c["command"] for c in result["commands"]], ["!stop", "!yes"])

    def test_dedupe_compares_exact_first_line(self):
        self.assertEqual(self.send("SECURITY", "Token leak in CI")[0], 0)
        self.assertEqual(self.send("SECURITY", "Token leak"), (0, "sent: [SECURITY] Token leak"))
        self.assertEqual(len(self.fake.sent), 2)
        self.assertIn("duplicate", self.send("SECURITY", "Token leak")[1])
        self.assertEqual(len(self.fake.sent), 2)

    def test_dedupe_ignores_header_in_body(self):
        alarm.alarm(CFG, "OUTAGE", "Routine strategy silent", "see also [SECURITY] Token leak", "", "", LIMITS)
        self.assertEqual(self.send("SECURITY", "Token leak")[1], "sent: [SECURITY] Token leak")
        self.assertEqual(len(self.fake.sent), 2)

    def filler(self, n, start=0, author=None):
        """n bot messages, newest first, with ids counting down from start + n."""
        return [{"id": str(start + n - i), "content": "🔴 [OUTAGE] x", "author": author or {"bot": True},
                 "timestamp": "2026-05-10T09:00:00Z"} for i in range(n)]

    def owner(self, mid, text):
        return {"id": mid, "content": text, "author": {"id": "42"}, "timestamp": "2026-05-01T09:00:00Z"}

    def test_stop_found_on_second_page(self):
        self.fake.history = self.filler(alarm.PAGE, start=10) + [self.owner("2", "!stop"), self.owner("1", "!start")]
        result = alarm.commands(CFG)
        self.assertEqual((result["stop"], result["stop_state"]), (True, "active"))

    def test_stop_page_limit_is_unknown(self):
        self.fake.history = self.filler(alarm.PAGE * 3, start=10) + [self.owner("1", "!stop")]
        result = alarm.commands(CFG, pages=3)
        self.assertEqual((result["stop"], result["stop_state"]), (None, "unknown"))
        self.assertIn("300", result["stop_reason"])
        self.assertIn("send !start", result["stop_reason"])
        self.assertTrue(alarm.commands(CFG, pages=4)["stop"])

    def test_stop_fetch_error_is_unknown(self):
        self.fake.history = self.filler(alarm.PAGE, start=10) + [self.owner("1", "!stop")]
        real = self.fake

        def failing(cfg, method, url, data=None, bot=True):
            if "before=" in url:
                raise alarm.NoChannel("Discord HTTP 500")
            return real(cfg, method, url, data, bot)
        with mock.patch.object(alarm, "http", failing):
            result = alarm.commands(CFG)
        self.assertEqual((result["stop"], result["stop_state"]), (None, "unknown"))
        self.assertIn("HTTP 500", result["stop_reason"])
        self.assertTrue(result["stop_reason"].startswith("read error"))

    def test_no_stop_command_is_not_stopped(self):
        self.fake.history = self.filler(alarm.PAGE + 5, start=10) + [self.owner("1", "!yes 3")]
        result = alarm.commands(CFG)
        self.assertEqual((result["stop"], result["stop_state"]), (False, "inactive"))
        self.assertEqual([c["command"] for c in result["commands"]], ["!yes"])

    def test_commands_cli_exit_code(self):
        self.fake.history = self.filler(alarm.PAGE * alarm.STOP_PAGES)
        env = {"DISCORD_BOT_TOKEN": "t", "DISCORD_CHANNEL_ID": "1", "DISCORD_OWNER_ID": "42"}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(alarm.main(["commands"]), 3)
        self.assertIsNone(json.loads(out.getvalue())["stop"])
        self.fake.history = []
        with mock.patch.dict("os.environ", env), redirect_stdout(io.StringIO()):
            self.assertEqual(alarm.main(["commands"]), 0)

    def test_acknowledged_commands_hidden(self):
        self.fake.history = [{"id": "1", "content": "!stop", "author": {"id": "42"}, "timestamp": "2026-05-10T10:00:00Z",
                              "reactions": [{"me": True, "emoji": {"name": alarm.ACK}}]}]
        self.assertEqual(alarm.commands(CFG)["commands"], [])
        self.assertEqual(len(alarm.commands(CFG, True)["commands"]), 1)

    def test_commands_need_owner(self):
        with self.assertRaises(alarm.NoChannel):
            alarm.commands(dict(CFG, owner=""))

    def test_status_reply_is_not_an_alert(self):
        for i in range(ALERT_BUDGET):
            self.send(title=f"a{i}")
        self.assertEqual(alarm.status(CFG, "All routines ok."), (0, "status sent"))
        self.assertTrue(self.fake.sent[-1].startswith("ℹ️ [STATUS]"))
        self.assertNotIn("<@42>", self.fake.sent[-1])
        self.assertEqual(self.send(title="over budget")[0], 4)  # the budget counts the alerts only
        self.assertEqual(alarm.status(dict(CFG, token="", channel=""), "x")[0], 2)
        for i in range(2):
            alarm.status(CFG, "again")
        self.assertEqual(self.send("OUTAGE", "fresh")[0], 4)

    def test_webhook_url_with_query(self):
        urls = []

        def capture(cfg, method, url, data=None, bot=True):
            urls.append(url)
        hook = dict(CFG, token="", channel="", webhook="https://hooks.example.com/w/1")
        with mock.patch.object(alarm, "http", capture):
            alarm.send_text(hook, "a")
            alarm.send_text(dict(hook, webhook=hook["webhook"] + "?thread_id=5"), "b")
        self.assertEqual(urls, ["https://hooks.example.com/w/1?wait=true",
                                "https://hooks.example.com/w/1?thread_id=5&wait=true"])

    def main(self, argv, env):
        out, err = io.StringIO(), io.StringIO()
        base = {k: "" for k in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID", "DISCORD_OWNER_ID",
                                "DISCORD_WEBHOOK_URL", "DISCORD_AUTH_PROXY")}
        with mock.patch.dict("os.environ", base | env), redirect_stdout(out), redirect_stderr(err):
            code = alarm.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_commands_not_configured_vs_partial_setup(self):
        code, out, _ = self.main(["commands"], {})
        self.assertEqual((code, json.loads(out)["stop_state"]), (2, "not_configured"))
        code, out, _ = self.main(["commands"], {"DISCORD_WEBHOOK_URL": "https://hooks.example.com/w/1"})
        self.assertEqual((code, json.loads(out)["stop_state"]), (2, "not_configured"))  # a webhook cannot read
        code, out, _ = self.main(["commands"], {"DISCORD_BOT_TOKEN": "t", "DISCORD_CHANNEL_ID": "1"})  # no owner
        result = json.loads(out)
        self.assertEqual((code, result["stop_state"], result["stop"]), (3, "unknown", None))
        self.assertTrue(result["stop_reason"].startswith("configuration error"))
        # A webhook plus the owner id is a half-finished bot setup: the owner expects !stop to work, so the
        # STOP state is unknown (fail closed), not "chat not used".
        code, out, _ = self.main(["commands"], {"DISCORD_WEBHOOK_URL": "https://hooks.example.com/w/1",
                                                "DISCORD_OWNER_ID": "42"})
        result = json.loads(out)
        self.assertEqual((code, result["stop_state"]), (3, "unknown"))
        self.assertTrue(result["stop_reason"].startswith("configuration error"))
        env = {"DISCORD_BOT_TOKEN": "t", "DISCORD_CHANNEL_ID": "1", "DISCORD_OWNER_ID": "42"}
        with mock.patch.object(alarm, "commands", mock.Mock(side_effect=KeyError("id"))):
            code, out, _ = self.main(["commands"], env)
        self.assertEqual((code, json.loads(out)["stop_state"]), (3, "unknown"))
        self.assertTrue(json.loads(out)["stop_reason"].startswith("unexpected error"))

    def test_errors_map_to_plan_b(self):
        env = {"DISCORD_BOT_TOKEN": "t", "DISCORD_CHANNEL_ID": "1", "DISCORD_OWNER_ID": "42"}
        argv = ["send", "--code", "OUTAGE", "--title", "t", "--body", "b"]
        (self.root / kit.LIMITS).write_text("{broken", encoding="utf-8")
        code, _, err = self.main(argv, env)
        self.assertEqual(code, 2)
        self.assertIn("configuration error", err)
        self.assertEqual(self.main(["desk", "--body", "b"], env)[0], 2)
        self.write_limits(LIMITS)
        with mock.patch.object(alarm, "alarm", mock.Mock(side_effect=ZeroDivisionError("boom"))):
            code, _, err = self.main(argv, env)
        self.assertEqual(code, 2)
        self.assertIn("unexpected error", err)
        self.assertEqual(self.main(argv, env)[0], 0)
        self.assertEqual(self.main(["status", "--body", "ok"], env)[0], 0)

    def test_long_message_truncated(self):
        alarm.send_text(CFG, "x" * 5000)
        self.assertEqual(len(self.fake.sent[0]), alarm.MAX_LEN)


class TestGuardianRunner(Base):
    def test_plan_b_creates_issue_once(self):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            return "[]"
        with mock.patch.object(guardian, "gh", fake_gh):
            guardian.plan_b("o/r", {"code": "OUTAGE", "title": "x", "body": "b"}, "no discord")
        self.assertEqual(calls[1][:2], ("issue", "create"))

        calls.clear()

        def fake_gh_existing(*args):
            calls.append(args)
            return json.dumps([{"title": "[OUTAGE] x"}])
        with mock.patch.object(guardian, "gh", fake_gh_existing):
            guardian.plan_b("o/r", {"code": "OUTAGE", "title": "x", "body": "b"}, "no discord")
        self.assertEqual([c[:2] for c in calls], [("issue", "list")])  # the open issue is not duplicated

    def test_empty_owner_login_fails_before_reading_history(self):
        self.write_limits(dict(LIMITS, owner={"github": ""}))
        calls, err = [], io.StringIO()
        with mock.patch.object(guardian, "gh", lambda *a: calls.append(a) or "[]"), \
                mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "o/r"}), redirect_stderr(err):
            self.assertEqual(guardian.main(), 2)
        self.assertEqual(calls, [])
        self.assertIn("owner.github", err.getvalue())

    def run_guardian(self, gh_state):
        """One guardian run against a fake `gh`; gh_state holds pulses and created issues."""
        def fake_gh(*args):
            if args[:2] == ("issue", "list") and "type:pulse" in args:
                return json.dumps(gh_state["pulses"])
            if args[:2] == ("issue", "list"):
                return json.dumps([{"title": t} for t in gh_state["issues"]])
            if args[:2] == ("issue", "create"):
                gh_state["issues"].append(args[args.index("--title") + 1])
            return "[]"
        env = {"GITHUB_REPOSITORY": "o/r", "DISCORD_BOT_TOKEN": "", "DISCORD_CHANNEL_ID": "",
               "DISCORD_WEBHOOK_URL": "", "DISCORD_AUTH_PROXY": ""}
        with mock.patch.object(guardian, "gh", fake_gh), mock.patch.object(guardian, "ensure_labels", lambda r: None), \
                mock.patch.dict("os.environ", env), redirect_stdout(io.StringIO()):
            guardian.main()

    def test_consecutive_runs_one_outage(self):
        state = {"pulses": [pulse_issue("operations", SILENT_H), pulse_issue("strategy", 2)], "issues": []}
        self.run_guardian(state)  # no Discord configured -> plan B issue
        with mock.patch.dict("os.environ", {"KIT_NOW": "2026-05-10T13:00:00Z"}):
            self.run_guardian(state)  # one hour later, operations still silent
        self.assertEqual([t for t in state["issues"] if t.startswith("[OUTAGE]")], ["[OUTAGE] Routine operations silent"])

        fake = FakeDiscord()  # with Discord: one chat alert, the second run is a duplicate
        with mock.patch.object(alarm, "http", fake):
            for now in ("2026-05-10T12:00:00Z", "2026-05-10T13:00:00Z"):
                with mock.patch.dict("os.environ", {"KIT_NOW": now}):
                    for a in kit.assess_guardian(state["pulses"], [], LIMITS, kit.now_utc(), False, None)["alerts"]:
                        self.assertEqual(alarm.alarm(CFG, a["code"], a["title"], a["body"], "", "", LIMITS)[0], 0)
        self.assertEqual(len(fake.sent), 1)

    def test_constitution_history_pages_to_owner_commit(self):
        pages = {1: [commit("agent", "c")] * 100, 2: [commit("agent", "e"), commit("owner", "d")]}
        calls = []

        def fake_gh(*args):
            page = int(re.search(r"page=(\d+)$", args[1]).group(1))
            calls.append(page)
            return json.dumps(pages.get(page, []))
        with mock.patch.object(guardian, "gh", fake_gh):
            commits, complete = guardian.constitution_history("o/r", "owner")
        self.assertEqual((len(commits), complete, calls), (102, True, [1, 2]))

        pages = {i: [commit("agent", "c")] * 100 for i in range(1, guardian.MAX_PAGES + 2)}
        with mock.patch.object(guardian, "gh", fake_gh):
            commits, complete = guardian.constitution_history("o/r", "owner")
        self.assertEqual((len(commits), complete), (100 * guardian.MAX_PAGES, False))

    def test_pulse_text(self):
        text = guardian.pulse_text({"alerts": [{"code": "CAP", "title": "t"}], "warnings": ["w"]})
        self.assertIn("alerts: 1, warnings: 1", text)
        self.assertEqual(kit.tags(text)[0][1]["routine"], "GUARDIAN")

    def test_labels_file_valid(self):
        labels = json.loads((TOOLS / "labels.json").read_text(encoding="utf-8"))
        self.assertTrue(all({"name", "color", "description"} <= set(l) for l in labels))
        self.assertEqual(len({l["name"] for l in labels}), len(labels))


class TestNoPersonalData(unittest.TestCase):
    """Guard for any copy of the kit: no personal or company identifiers in its files.

    The list of forbidden phrases is deliberately NOT stored in the repo (it would itself contain the
    identifiers it is meant to keep out). Supply it from CI of your own installation:
    KIT_FORBIDDEN="phrase one,phrase two" (comma-separated, case-insensitive substrings).
    Without the variable only generic checks run.
    """

    GENERIC_PLAIN = ["discord.com/channels"]
    GENERIC_REGEX = [
        re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]+"),  # webhook URL
        re.compile(r"\b[MNO][\w-]{23,25}\.[\w-]{6}\.[\w-]{27,}\b"),  # bot token shape
        # any e-mail address except the example.* / .test / .invalid / .localhost placeholder domains
        re.compile(r"(?i)\b[\w.+-]+@(?!(?:[\w-]+\.)*(?:example\.[a-z]+|[\w-]+\.(?:test|invalid|localhost|example))"
                   r"(?![\w-]|\.[\w-]))[\w-]+(?:\.[\w-]+)+"),
    ]

    @staticmethod
    def forbidden():
        raw = os.environ.get("KIT_FORBIDDEN", "")
        return [w.strip().lower() for w in raw.split(",") if w.strip()]

    def test_scan(self):
        base = TOOLS.parent
        skip = {"test_kit.py"}
        words = self.GENERIC_PLAIN + self.forbidden()
        hits = []
        for path in base.rglob("*"):
            if not path.is_file() or path.name in skip or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            text = raw.lower()
            rel = path.relative_to(base)
            hits += [f"{rel}: forbidden phrase #{i}" for i, w in enumerate(words) if w in text]
            hits += [f"{rel}: generic pattern #{i}" for i, rx in enumerate(self.GENERIC_REGEX) if rx.search(raw)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
