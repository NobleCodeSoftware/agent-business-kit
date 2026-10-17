import io
import json
import os
import re
import sys
import tempfile
import unittest
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
        bad["routines"]["OPS"]["max_silence_h"] = "x"
        errors = kit.check_limits(bad)
        self.assertEqual(len(errors), 3)

    def test_missing_limits_is_config_error(self):
        (self.root / kit.LIMITS).unlink()
        self.assertEqual(run(["state", "check"])[0], 1)
        self.assertEqual(run(["cap"])[0], 2)

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

    def test_negative_requires_correction(self):
        self.add()
        self.assertEqual(self.add(tid="r1", amount="-10")[0], 1)
        self.assertEqual(self.add("--correction-of", "1", tid="r1", amount="-10")[0], 0)

    def test_cap_thresholds(self):
        self.add(amount="720")
        status = kit.revenue_status(date(2026, 5, 10))
        self.assertEqual((status["percent"], status["threshold"], status["remaining"]), (72.0, 0.7, "280.00"))
        self.assertEqual(kit.revenue_status(date(2026, 8, 1))["revenue"], "0.00")  # next period

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
        return kit.tag("lease", {"shift": "OPS-1", "until": until, "attempt": attempt})

    def test_lease_command_roundtrip(self):
        code, out, _ = run(["lease", "--shift", "OPS-1"])
        self.assertEqual(code, 0)
        self.assertIn("2026-05-10T18:00:00Z", out)
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

    def test_intent_result_pulse(self):
        self.assertIn("kit:intent", run(["intent", "--id", "x", "--description", "d"])[1])
        self.assertIn("❌", run(["result", "--id", "x", "--status", "error"])[1])
        out = run(["pulse", "--routine", "OPS", "--status", "ok", "--description", "fine"])[1]
        self.assertEqual(kit.tags(out)[0][1]["routine"], "OPS")


GOOD_DESK = """# [DESK] Register a domain — 12 USD — due 2026-05-20

**Urgency:** normal    **Department:** BIZ

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

    def test_cli(self):
        f = self.root / "item.md"
        f.write_text(GOOD_DESK, encoding="utf-8")
        self.assertEqual(run(["desk", "check", str(f)])[0], 0)
        f.write_text("# not a desk item", encoding="utf-8")
        self.assertEqual(run(["desk", "check", str(f)])[0], 1)


def pulse_issue(routine, hours_ago, status="ok"):
    t = kit.now_utc() - timedelta(hours=hours_ago)
    return {"title": f"Pulse: {routine}",
            "body": kit.tag("pulse", {"routine": routine, "status": status, "time": kit.iso(t)})}


class TestGuardian(Base):
    def assess(self, pulses, commits=None, stop=False, cap=None):
        return kit.assess_guardian(pulses, commits if commits is not None else [{"sha": "a" * 40, "author": {"login": "owner"}}],
                                   LIMITS, kit.now_utc(), stop, cap)

    def test_healthy(self):
        r = self.assess([pulse_issue("OPS", 2), pulse_issue("BIZ", 5)])
        self.assertEqual((r["alerts"], r["warnings"]), ([], []))

    def test_ops_outage_alerts_after_threshold(self):
        r = self.assess([pulse_issue("OPS", 16), pulse_issue("BIZ", 2)])
        self.assertEqual([a["code"] for a in r["alerts"]], ["OUTAGE"])
        r = self.assess([pulse_issue("OPS", 13), pulse_issue("BIZ", 2)])
        self.assertEqual(r["alerts"], [])
        self.assertTrue(any("OPS" in w for w in r["warnings"]))

    def test_all_silent(self):
        r = self.assess([pulse_issue("OPS", 40), pulse_issue("BIZ", 40)])
        self.assertIn("All routines silent", [a["title"] for a in r["alerts"]])

    def test_stuck_shift_warning(self):
        r = self.assess([pulse_issue("OPS", 5, "in-progress")])
        self.assertTrue(any("interrupted" in w for w in r["warnings"]))

    def test_constitution_tampering(self):
        # The GitHub API lists newest first. Agent commits before the owner's approval are tolerated.
        commits = [{"sha": "b" * 40, "author": {"login": "owner"}}, {"sha": "c" * 40, "author": {"login": "agent"}}]
        self.assertEqual(self.assess([], commits)["alerts"], [])
        commits = [{"sha": "c" * 40, "author": {"login": "agent"}}, {"sha": "b" * 40, "author": {"login": "owner"}}]
        self.assertEqual(self.assess([], commits)["alerts"][0]["code"], "SECURITY")

    def test_no_owner_commit_and_no_history(self):
        self.assertIn("not approved", self.assess([], [{"sha": "a" * 40, "author": {"login": "x"}}])["warnings"][0])
        empty = kit.assess_guardian([], [], LIMITS, kit.now_utc(), False, None)
        self.assertIn("No history", empty["warnings"][0])

    def test_stop_skips_pulse_checks(self):
        r = self.assess([pulse_issue("OPS", 99)], stop=True)
        self.assertTrue(r["stop"])
        self.assertEqual(r["alerts"], [])

    def test_cap_alert(self):
        cap = {"period": "2026-P2", "revenue": "960", "limit": "1000", "percent": 96.0, "threshold": 0.95}
        self.assertEqual(self.assess([], cap=cap)["alerts"][0]["code"], "CAP")
        cap.update(threshold=0.85, percent=86.0)
        self.assertEqual(self.assess([], cap=cap)["alerts"], [])


class FakeDiscord:
    """Replaces alarm.http with an in-memory channel."""

    def __init__(self):
        self.sent, self.reactions, self.history = [], [], []

    def __call__(self, cfg, method, url, data=None, bot=True):
        if method == "GET":
            return self.history
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
        for i in range(3):
            self.assertEqual(self.send(title=f"a{i}")[0], 0)
        self.assertEqual(self.send(title="a4")[0], 4)
        self.assertEqual(self.send("SECURITY", "leak")[0], 0)

    def test_no_config_is_plan_b(self):
        empty = dict(CFG, token="", channel="")
        self.assertEqual(alarm.alarm(empty, "LEGAL", "t", "b", "", "", LIMITS)[0], 2)

    def test_desk_once_a_day(self):
        self.assertEqual(alarm.desk(CFG, "1 item", LIMITS)[1], "desk notice sent")
        self.assertIn("already sent", alarm.desk(CFG, "2 items", LIMITS)[1])

    def test_owner_commands_only(self):
        self.fake.history = [
            {"id": "3", "content": "!yes 12", "author": {"id": "42"}, "timestamp": "2026-05-10T11:00:00Z"},
            {"id": "2", "content": "!start", "author": {"id": "99"}, "timestamp": "2026-05-10T10:30:00Z"},
            {"id": "1", "content": "!stop", "author": {"id": "42"}, "timestamp": "2026-05-10T10:00:00Z"}]
        result = alarm.commands(CFG)
        self.assertTrue(result["stop"])  # the stranger's !start is ignored
        self.assertEqual([c["command"] for c in result["commands"]], ["!stop", "!yes"])

    def test_acknowledged_commands_hidden(self):
        self.fake.history = [{"id": "1", "content": "!stop", "author": {"id": "42"}, "timestamp": "2026-05-10T10:00:00Z",
                              "reactions": [{"me": True, "emoji": {"name": alarm.ACK}}]}]
        self.assertEqual(alarm.commands(CFG)["commands"], [])
        self.assertEqual(len(alarm.commands(CFG, True)["commands"]), 1)

    def test_commands_need_owner(self):
        with self.assertRaises(alarm.NoChannel):
            alarm.commands(dict(CFG, owner=""))

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

        def fake_gh_existing(*args):
            return json.dumps([{"title": "[OUTAGE] x"}])
        with mock.patch.object(guardian, "gh", fake_gh_existing):
            guardian.plan_b("o/r", {"code": "OUTAGE", "title": "x", "body": "b"}, "no discord")

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
