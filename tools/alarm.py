#!/usr/bin/env python3
"""alarm - emergency channel from the agents to the owner (Discord bot) with a plan B.

Usage rules: processes/ESCALATION.md. Configuration through environment variables:
  DISCORD_CHANNEL_ID, DISCORD_OWNER_ID  - full mode (send + owner commands), plus one of:
    DISCORD_BOT_TOKEN=<token>           - token in a variable (GitHub Actions),
    DISCORD_AUTH_PROXY=1                - token held as a network secret by the environment proxy,
                                          which adds the Authorization header for discord.com,
                                          so the token never reaches the agent's machine;
  DISCORD_WEBHOOK_URL                   - fallback mode (send only).

Exit codes:
  0 - sent, or duplicate skipped,
  2 - missing configuration or Discord error -> open an issue labelled `type:incident` and `urgent`,
  4 - daily alert budget exhausted -> open an `urgent` issue instead of a message.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import kit

CODES = ("SECURITY", "LEGAL", "CUSTOMER", "ACCOUNT", "CAP", "OUTAGE", "DESK")
ACK = "✅"
UA = "DiscordBot (https://github.com/NobleCodeSoftware/agent-business-kit, 1.0)"
MAX_LEN = 2000


class NoChannel(Exception):
    """Discord not configured or unreachable - use plan B (issue)."""


def configuration() -> dict:
    return {
        "token": os.environ.get("DISCORD_BOT_TOKEN", "").strip(),
        "channel": os.environ.get("DISCORD_CHANNEL_ID", "").strip(),
        "owner": os.environ.get("DISCORD_OWNER_ID", "").strip(),
        "webhook": os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
        "proxy": os.environ.get("DISCORD_AUTH_PROXY", "").strip() == "1",
        "api": os.environ.get("DISCORD_API", "https://discord.com/api/v10").rstrip("/"),
    }


def bot_mode(cfg: dict) -> bool:
    return bool(cfg["channel"] and (cfg["token"] or cfg.get("proxy")))


def _safe(url: str) -> str:
    """URL for error messages: no query string, and no webhook token."""
    url = url.split("?")[0]
    return url.split("/webhooks/")[0] + "/webhooks/<redacted>" if "/webhooks/" in url else url


def http(cfg: dict, method: str, url: str, data: dict | None = None, bot: bool = True):
    headers = {"User-Agent": UA}
    if bot and cfg["token"]:  # in proxy mode the environment proxy adds the header
        headers["Authorization"] = f"Bot {cfg['token']}"
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(2):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode()
            try:
                return json.loads(raw) if raw else None
            except ValueError:
                raise NoChannel(f"Discord: invalid response for {method} {_safe(url)}")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                try:
                    wait = float(json.loads(e.read().decode()).get("retry_after", 1))
                except (ValueError, AttributeError):
                    wait = 1.0
                time.sleep(min(wait, 5.0))
                continue
            raise NoChannel(f"Discord HTTP {e.code} for {method} {_safe(url)}")
        except OSError as e:  # URLError, timeout, dropped connection
            raise NoChannel(f"Discord unreachable: {e}")
    raise NoChannel("Discord: rate limit exceeded")


def messages(cfg: dict, count: int = 100) -> list[dict]:
    """Latest channel messages, newest first."""
    return http(cfg, "GET", f"{cfg['api']}/channels/{cfg['channel']}/messages?limit={count}") or []


def message_time(m: dict) -> datetime:
    return kit.parse_time(m["timestamp"])


def local_midnight(now: datetime, limits: dict | None = None) -> datetime:
    local = now.astimezone(kit.tz(limits))
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def send_text(cfg: dict, text: str) -> None:
    text = text if len(text) <= MAX_LEN else text[:MAX_LEN - 1] + "…"
    mentions = {"parse": [], "users": [cfg["owner"]] if cfg["owner"] else []}
    if bot_mode(cfg):
        http(cfg, "POST", f"{cfg['api']}/channels/{cfg['channel']}/messages",
             {"content": text, "allowed_mentions": mentions})
    elif cfg["webhook"]:
        http(cfg, "POST", f"{cfg['webhook']}?wait=true", {"content": text, "allowed_mentions": mentions}, bot=False)
    else:
        raise NoChannel("no DISCORD_CHANNEL_ID with a token (DISCORD_BOT_TOKEN or DISCORD_AUTH_PROXY=1) "
                        "and no DISCORD_WEBHOOK_URL")


def alarm(cfg: dict, code: str, title: str, body: str, needs: str, issue: str, limits: dict) -> tuple[int, str]:
    if not bot_mode(cfg) and not cfg["webhook"]:
        return 2, "Discord not configured - use plan B (`urgent` issue)"
    header = f"[{code}] {title}"
    now = kit.now_utc()
    if bot_mode(cfg):
        recent = [m for m in messages(cfg) if (m.get("author") or {}).get("bot")]
        silence = timedelta(hours=limits["alerts"]["repeat_silence_h"])
        if any(header in m.get("content", "") and now - message_time(m) < silence for m in recent):
            return 0, f"duplicate skipped: {header}"
        today_alerts = [m for m in recent if m.get("content", "").startswith("🔴 [")
                        and not m["content"].startswith("🔴 [SECURITY]")
                        and message_time(m) >= local_midnight(now, limits)]
        if code != "SECURITY" and len(today_alerts) >= limits["alerts"]["max_per_day"]:
            return 4, "daily alert budget exhausted - use an `urgent` issue"
    mention = f"\n<@{cfg['owner']}>" if cfg["owner"] else ""
    lines = [f"🔴 {header}", body.strip(), f"**Needed from you:** {needs or 'nothing - for information, we are on it'}"]
    if issue:
        lines.append(f"Issue: {issue}")
    send_text(cfg, "\n".join(lines) + mention)
    return 0, f"sent: {header}"


def desk(cfg: dict, body: str, limits: dict | None = None) -> tuple[int, str]:
    """Batched notice about new desk items - at most once per local day."""
    if not bot_mode(cfg) and not cfg["webhook"]:
        return 2, "Discord not configured"
    if bot_mode(cfg):
        now = kit.now_utc()
        if any((m.get("author") or {}).get("bot") and m.get("content", "").startswith("📥 [DESK]")
               and message_time(m) >= local_midnight(now, limits) for m in messages(cfg)):
            return 0, "today's desk notice already sent - skipped"
    send_text(cfg, f"📥 [DESK] New items on your desk\n{body.strip()}")
    return 0, "desk notice sent"


def commands(cfg: dict, include_all: bool = False) -> dict:
    """Owner commands (!stop, !start, !status, !yes N, !no N) from the alert channel."""
    if not bot_mode(cfg) or not cfg["owner"]:
        raise NoChannel("commands need DISCORD_CHANNEL_ID, DISCORD_OWNER_ID and a bot token")
    from_owner = [m for m in messages(cfg) if (m.get("author") or {}).get("id") == cfg["owner"]]
    stop, out, empty = None, [], 0
    for m in reversed(from_owner):  # oldest first
        text = (m.get("content") or "").strip()
        if not text:
            empty += 1
            continue
        if not text.startswith("!"):
            continue
        parts = text.split()
        command, argument = parts[0].lower(), " ".join(parts[1:])
        if command in ("!stop", "!start"):
            stop = command == "!stop"
        done = any(r.get("me") and (r.get("emoji") or {}).get("name") == ACK for r in m.get("reactions") or [])
        if include_all or not done:
            out.append({"id": m["id"], "time": m["timestamp"], "command": command,
                        "argument": argument, "processed": done})
    result = {"stop": bool(stop), "commands": out}
    if empty:
        result["note"] = (f"{empty} owner messages have no content - enable Message Content Intent "
                          "in the Discord Developer Portal (Bot -> Privileged Gateway Intents)")
    return result


def acknowledge(cfg: dict, message_id: str) -> None:
    emoji = urllib.parse.quote(ACK)
    http(cfg, "PUT", f"{cfg['api']}/channels/{cfg['channel']}/messages/{message_id}/reactions/{emoji}/@me")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="alarm", description="Emergency channel (Discord)")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("send", help="emergency alert (closed list of codes)")
    s.add_argument("--code", choices=CODES, required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--body", required=True)
    s.add_argument("--needs", default="", help="what the owner must do (empty = nothing)")
    s.add_argument("--issue", default="", help="link to the issue")
    d = sub.add_parser("desk", help="batched desk notice (once per day)")
    d.add_argument("--body", required=True)
    c = sub.add_parser("commands", help="owner commands, JSON")
    c.add_argument("--all", action="store_true", help="include already acknowledged ones")
    a = sub.add_parser("ack", help="mark a command as processed (reaction)")
    a.add_argument("--id", required=True)
    sub.add_parser("test", help="test message after configuration")
    args = p.parse_args(argv)

    cfg = configuration()
    try:
        if args.command == "send":
            code, message = alarm(cfg, args.code, args.title, args.body, args.needs, args.issue, kit.load_limits())
        elif args.command == "desk":
            code, message = desk(cfg, args.body, kit.load_limits())
        elif args.command == "commands":
            print(json.dumps(commands(cfg, args.all), ensure_ascii=False, indent=2))
            return 0
        elif args.command == "ack":
            acknowledge(cfg, args.id)
            code, message = 0, f"acknowledged {args.id}"
        else:
            send_text(cfg, "✅ Connection test: the alert channel works. Nothing to do.")
            code, message = 0, "test message sent"
    except NoChannel as e:
        print(f"plan B: {e}", file=sys.stderr)
        return 2
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
