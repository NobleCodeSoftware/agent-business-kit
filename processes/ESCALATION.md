# Escalation and alerts

Contact the owner **only in emergencies**. Every alert spends their trust, so we wake them only when
delay costs real money, legal standing or security.

## When we alert (closed list)

| Code | Situation | Example |
|---|---|---|
| `SECURITY` | Security incident | leaked secret, account takeover, suspicious transaction, **actively exploited vulnerability in our product** (many regimes require a report within 24 h; the owner files it) |
| `LEGAL` | Letter from an authority, legal claim, accusation of infringement | summons, takedown notice, consumer-agency complaint |
| `CUSTOMER` | A statutory deadline toward a customer expires within 48 h | complaint, withdrawal from a contract |
| `ACCOUNT` | Suspension or block of a sales or payment account | ban, withheld payouts |
| `CAP` | Revenue passed 95% of the optional ceiling in `limits.json` | - |
| `OUTAGE` | The business is down: OPS silent for longer than `routines.OPS.alert_after_h` (at least two shifts missed in a row) or every routine silent | - |
| `DESK` | A desk item has a deadline under 48 h and revenue or compliance depends on it | domain renewal |

Everything else goes to the desk or the report, **not** to an alert.

## How we alert

```bash
python3 tools/alarm.py send --code OUTAGE --title "Routine OPS silent for 16 h" \
  --body "Last OPS pulse: 2099-01-05 09:12. BIZ and FIN are running." --issue "#12"
```

- Primary channel: a Discord bot. Configuration: `DISCORD_CHANNEL_ID`, `DISCORD_OWNER_ID` and a bot
  token. In a Claude cloud environment the token can be a "network secret" for `discord.com`
  (`DISCORD_AUTH_PROXY=1`), so it never reaches the agent's machine. In GitHub Actions it is a repo
  secret (`DISCORD_BOT_TOKEN`). A webhook (`DISCORD_WEBHOOK_URL`) works as a send-only fallback.
- Deduplication: the same code and title are not sent again for `alerts.repeat_silence_h` hours.
- Daily cap: `alerts.max_per_day`. `SECURITY` has no cap.
- **Plan B:** if Discord is unavailable (missing secrets, API error) `alarm.py` exits with code 2.
  The agent then opens an issue labelled `type:incident` and `urgent`, and records the lack of contact
  with the owner in the pulse. Exit code 4 (daily cap) also means: open an `urgent` issue.

## Message format

```
🔴 [OUTAGE] Routine OPS silent for 16 h
Last OPS pulse: 2099-01-05 09:12. BIZ and FIN are running.
**Needed from you:** nothing - for information, we are on it
Issue: #12
@owner
```

Every alert says whether the owner **must** do something. If not, it is only information that we have
a problem and are solving it.

## Owner commands in chat

Agents accept commands only from the account in `DISCORD_OWNER_ID`, never from other users or bots:

| Command | Effect |
|---|---|
| `!stop` | kill switch: shifts end without external actions |
| `!start` | resume after `!stop` |
| `!status` | OPS answers with the state of the business at the next shift |
| `!yes <n>` / `!no <n>` | decision on desk item number `<n>` |

Agents read commands at the start of every shift (`python3 tools/alarm.py commands`) and acknowledge
processed ones with `alarm.py ack`. There is no reading between shifts, so the delay is at most the gap
between OPS shifts. For an immediate stop, disable the routines in the platform UI.
