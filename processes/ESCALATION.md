# Escalation and alerts

Contact the owner **only in emergencies**. Every alert spends their trust, so we wake them only when
delay costs real money, legal standing or security.

## When we alert (closed list)

| Code | Situation | Example |
|---|---|---|
| `SECURITY` | Security incident | leaked secret, account takeover, suspicious transaction, **actively exploited vulnerability in our product** (some regimes require a report within 24 h; the owner files it) |
| `LEGAL` | Letter from an authority, legal claim, accusation of infringement | summons, takedown notice, consumer-agency complaint |
| `CUSTOMER` | A statutory deadline toward a customer expires within 48 h | complaint, withdrawal from a contract |
| `ACCOUNT` | Suspension or block of a sales or payment account | ban, withheld payouts |
| `CAP` | Revenue reached the highest of `revenue.alert_thresholds` (share of the optional ceiling) in `limits.json` | sent by the guardian only; Finance tells Strategy |
| `OUTAGE` | The business is down: the operations routine silent for longer than `routines.operations.alert_after_h` (at least two shifts missed in a row), the operations routine without any pulse while another routine has reported for that long, or every routine silent | - |
| `DESK` | A desk item has a deadline under 48 h and revenue or compliance depends on it | domain renewal |

Everything else goes to the desk or the report, **not** to an alert.

## How we alert

```bash
python3 tools/alarm.py send --code OUTAGE --title "Routine operations silent" \
  --body "No pulse for 17 h. Last operations pulse: 2099-01-05 08:12. Strategy and finance routines are running." \
  --issue "https://github.com/[OWNER]/[BUSINESS-REPO]/issues/123"
```

- Primary channel: a Discord bot. Configuration: `DISCORD_CHANNEL_ID`, `DISCORD_OWNER_ID` and a bot
  token. In a Claude cloud environment the token can be a "network secret" for `discord.com`
  (`DISCORD_AUTH_PROXY=1`), so it never reaches the agent's machine. In GitHub Actions it is a repo
  secret (`DISCORD_BOT_TOKEN`). A webhook (`DISCORD_WEBHOOK_URL`) works as a send-only fallback.
- A network secret keeps the token off the agent's machine, but the agent can still use it for any
  request to `discord.com`. Give the bot permissions in one private channel only (send, read, react)
  and no server-level permissions.
- Deduplication: the same code and title are not sent again for `alerts.repeat_silence_h` hours. Only
  an exact match of the alert's first line (`🔴 [CODE] title`) counts as a duplicate, so keep titles
  stable and put changing details (hours, amounts) in the body.
- Daily cap: `alerts.max_per_day`. `SECURITY` has no cap.
- Deduplication, the daily cap and the once-a-day desk notice need bot mode (channel id plus token),
  because they read the channel history. With only a webhook configured, they do not work: every call
  sends a message. Owner commands also need bot mode.
- **Plan B:** if Discord is unavailable (missing secrets, API error) `alarm.py` exits with code 2.
  The agent then opens an issue labelled `type:incident` and `urgent`, and records the lack of contact
  with the owner in the pulse. Exit code 4 (daily cap) also means: open an `urgent` issue.

## Message format

```
🔴 [OUTAGE] Routine operations silent
No pulse for 17 h. Last operations pulse: 2099-01-05 08:12. Strategy and finance routines are running.
**Needed from you:** nothing - for information, we are on it
Issue: https://github.com/[OWNER]/[BUSINESS-REPO]/issues/123
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
| `!status` | Operations answers with the state of the business at the next shift (`alarm.py status`, not counted as an alert) |
| `!yes <n>` / `!no <n>` | decision on desk item number `<n>` |

Agents read commands at the start of every shift (`python3 tools/alarm.py commands`) and acknowledge
processed ones with `alarm.py ack`. There is no reading between shifts, so the delay is at most the gap
between operations shifts. For an immediate stop, disable the routines in the platform UI.

The chat STOP state is the owner's latest `!stop` or `!start`, however far back in the channel it is:
`alarm.py commands` reads the history page by page (up to 1000 messages) until it finds one. Its JSON
has `"stop_state"`: `active`, `inactive` (the latest command is `!start`, or the whole channel history
was read and has no `!stop`/`!start` at all), or `unknown`. Then `"stop"` is `null`, `"stop_reason"`
says why, and the exit code is 3. Without any chat setup (Discord is optional) `"stop_state"` is
`not_configured` and the exit code is 2: shifts then rely on `constitution/STOP` alone. A partial
setup is not "not configured": as soon as any bot variable is set (`DISCORD_CHANNEL_ID`,
`DISCORD_OWNER_ID`, a bot token or `DISCORD_AUTH_PROXY`) without the full set, it reports `unknown`.
This includes a webhook plus `DISCORD_OWNER_ID`: the owner id shows that chat commands were meant to
work, so the shift stops rather than ignore a `!stop` that may have been sent.
The state is unknown when:

- the last 1000 messages contain no owner `!stop` or `!start`. This also happens to an owner who has
  never sent either command, once alerts have filled the channel past 1000 messages. Resume: send
  `!start` in the channel;
- the history could not be read (`stop_reason` starts with "read error"). Resume: fix the bot's
  configuration or wait for Discord; the next shift reads the state again;
- the chat setup is incomplete or `alarm.py` failed (`stop_reason` starts with "configuration error"
  or "unexpected error"). Resume: fix the configuration.

**An unknown STOP state stops the shift like an active STOP**: no external actions, end the shift.
The pulse is `degraded` (not `stop`, because the owner did not ask for a pause) with `stop_reason` in
its description. For a longer pause, use the file
`constitution/STOP` instead of `!stop`: it does not depend on the chat history. To resume, the owner
sends `!start` (chat STOP) or deletes the file (file STOP).
