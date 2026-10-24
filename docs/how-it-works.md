# How it works: one day of a business on the kit

This page walks through what happens in a business set up from this kit: who runs when, how a request
reaches the owner, what stops the business, and what watches it from outside. It only describes what
the kit's files define. Where a step is done by an agent following a prompt (not by a script), the page
says so.

## The moving parts

- **The owner** decides, pays and signs. They answer desk items with yes or no and can stop everything.
- **Three scheduled routines** (OPS, BIZ, FIN) wake permanent Claude Code sessions with a short "new
  shift" message (`routines/README.md`). Each session re-reads its prompt from the repo
  (`routines/OPS.md`, `routines/BIZ.md`, `routines/FIN.md`) and runs it.
- **The guardian** is a GitHub Actions workflow (`.github/workflows/guardian.yml`) that runs
  `tools/guardian.py` every hour. It uses no AI.
- **State** lives in the repo and in GitHub issues: tasks, desk items, incidents, pulses, experiments
  (`processes/TASKS.md`, `processes/RESILIENCE.md`, `processes/BUSINESS_DEVELOPMENT.md`). No session is expected to remember anything.
- **Rules** sit in `constitution/CONSTITUTION.md` and the numbers in `constitution/limits.json`.
  Agents may not change either.

## A day of scheduled shifts

The default schedule in `constitution/limits.json` (all times UTC):

| Time | What runs | Prompt / script |
|---|---|---|
| every hour at :23 | Guardian | `.github/workflows/guardian.yml` -> `tools/guardian.py` |
| 00:00 | OPS shift | `routines/OPS.md` |
| 06:00 | OPS shift | `routines/OPS.md` |
| 07:30 | BIZ shift (full mode on Mondays) | `routines/BIZ.md` |
| 12:00 | OPS shift | `routines/OPS.md` |
| 18:00 | OPS shift | `routines/OPS.md` |
| 20:30 | FIN shift | `routines/FIN.md` |

That is six routine runs per day, which matches `power.max_routine_runs_per_day`. OPS may move the
schedule within the bounds of `limits.json`; anything beyond them goes to the desk
(`processes/CHANGE.md`).

### What every shift does first

All three prompts share the same invariants:

1. Make sure the business repo is cloned; if that fails, end the shift.
2. Check STOP: `python3 tools/kit.py stop` (exit code 3 means STOP is active) and, for OPS and BIZ,
   `python3 tools/alarm.py commands` (field `stop`). If STOP is active, write a pulse with status
   `stop` and end without any external action.
3. Validate state with `python3 tools/kit.py state check`. It checks `limits.json`, the sales ledger
   (`finance/ledger.csv`), the cost log (`finance/costs.csv`) and the forecast log
   (`knowledge/calibration.csv`). If it fails, the shift takes no external actions, opens a
   `type:incident` issue, sets its pulse to `degraded` and ends.
4. At the end, replace the body of its pulse issue ("Pulse: OPS", "Pulse: BIZ", "Pulse: FIN", label
   `type:pulse`) with the output of `python3 tools/kit.py pulse --routine <NAME> --status ...`.

### OPS (four times a day)

The shift procedure in `routines/OPS.md`:

1. **Owner commands.** Read `!stop`, `!start`, `!yes N`, `!no N` from the alert channel, apply them,
   and acknowledge each with `python3 tools/alarm.py ack --id <id>`.
2. **Health.** Read the BIZ, FIN and GUARDIAN pulses. A stale pulse is treated as an incident.
3. **Leases.** Build a JSON list of `state:in-progress` tasks with their comments and run
   `python3 tools/kit.py tasks assess <file>`. For each task the tool answers `leave`,
   `return_to_queue` or `block`, and lists intents that have no recorded result.
4. **Desk.** Publish complete drafts, expire items past their deadline, send one batched notice
   (see the next section).
5. **Queue.** Take `state:new` tasks by priority (`p1-security-legal` first), claim each with a lease
   comment from `python3 tools/kit.py lease`, delegate to a department subagent
   (`docs/departments.md`), record `kit.py intent` before and `kit.py result` after each external
   action, and send work to QA review.
6. **Close.** Pulse, shift summary, and hand back unfinished tasks with a reason.

### BIZ (every morning)

Signal review into `knowledge/signals/<date>.md`, experiment cards updated, and forecasts whose
deadline has passed resolved in `knowledge/calibration.csv` (`outcome` set to 1 or 0). On Mondays:
portfolio review, a red-team subagent before any "scale" or "new experiment" decision, decision
records and a weekly report issue. On the last day of the month: a strategy memo and
`python3 tools/kit.py brier`. Details: `processes/BUSINESS_DEVELOPMENT.md`.

### FIN (every evening)

Record new sales with `python3 tools/kit.py ledger add` (a repeated channel and transaction id is
skipped, so reruns do not double-count), record approved costs with their desk item number, check the
optional revenue cap with `python3 tools/kit.py cap`, audit the OPS report against source data and
check the reserve rule. FIN never moves money.

## How a desk item flows

Anything only a human can do (payments, contracts, terms acceptance, account creation, refunds,
changes to `constitution/`) becomes a desk item: a `type:desk` issue written so the owner can answer
yes or no without searching or calculating (`processes/DESK.md`).

1. **Draft.** The department that needs the decision fills the template in `processes/DESK.md`.
   The title carries the action, the amount and a due date:
   `# [DESK] <action> — <amount> — due YYYY-MM-DD`.
2. **Checks by other departments.** FIN checks amounts, tax effects and funds for spending; QA
   reviews contracts and terms and lists key points and risks.
3. **Completeness gate.** OPS runs `python3 tools/kit.py desk check <file>`. It rejects a draft with
   a missing or empty mandatory section, a missing `**Urgency:**` line, leftover `<placeholder>`
   fields, or a due date in the past, and exits with code 1. Only a complete item is published.
   Compare `examples/desk-item.md` (complete) with `examples/desk-item-incomplete.md`.
4. **Notice.** OPS sends one batched notice per day with `python3 tools/alarm.py desk`
   (`desk.notification` is `once_a_day`). An item due in under 48 hours on which revenue or
   compliance depends goes out immediately as a `DESK` alert (`processes/ESCALATION.md`).
5. **Answer.** The owner comments `/yes`, `/no` or `/question ...` on the issue, or sends `!yes N` /
   `!no N` in chat. Chat answers are picked up at the next OPS shift and recorded on the issue.
6. **The owner acts.** On yes, the owner performs the steps and comments `done`. Agents run no
   transactions themselves.
7. **Verify and close.** The department checks the outcome (for example, that the account works),
   records it on the issue and closes it.

### "No answer" means no

`limits.json` sets `desk.default_deadline_days` (3) and `desk.no_answer: "decline"`;
`kit.py state check` rejects any other value for `desk.no_answer`. When the due date
passes without an answer, OPS closes the item with the label `result:expired` and the department does
what the item's "If you decline or do not answer" section says. Waiting for the desk never blocks
other work (`constitution/CONSTITUTION.md`, section 4). An absent owner slows spending; it does not
stop operations (`processes/RESILIENCE.md`, failure mode 9).

## The STOP switch

Three ways to stop, listed in `constitution/CONSTITUTION.md`, section 6:

1. Turn the routines off in the Claude Code UI. Immediate and needs no agent.
2. Send `!stop` in the alert channel from the owner's account. Read only at the start of a shift, so
   the delay is up to the gap between shifts.
3. Create the file `constitution/STOP` (any content). `kit.py stop` then exits with code 3.

While STOP is active, shifts write a `stop` pulse and do nothing else, and the guardian skips its pulse
and revenue-cap checks (it still checks the constitution). Only the owner resumes: `!start`, deleting
the file, or turning the routines back on.

## Escalation

The owner is alerted only for a closed list of codes: `SECURITY`, `LEGAL`, `CUSTOMER`, `ACCOUNT`,
`CAP`, `OUTAGE`, `DESK` (`processes/ESCALATION.md`). Everything else goes to the desk or a report.

- Alerts are sent with `python3 tools/alarm.py send --code ... --title ... --body ...` through a
  Discord bot (or a send-only webhook, which carries alerts only: owner commands such as `!stop` need
  the bot).
- The same code and title are not repeated within `alerts.repeat_silence_h` hours, and at most
  `alerts.max_per_day` alerts go out per day. `SECURITY` has no cap.
- **Plan B:** exit code 2 (Discord not configured or failing) or 4 (daily cap reached) means the agent
  opens an issue labelled `type:incident` and `urgent` instead.
- Owner commands are accepted only from the account in `DISCORD_OWNER_ID`.

## The guardian

`tools/guardian.py` runs hourly in GitHub Actions, outside the Claude subscription, so it still works
when the agents have hit a usage limit. It is off until you set the repository variable
`GUARDIAN_ENABLED` to `true`. Each run:

1. Creates any missing labels from `tools/labels.json`.
2. Reads the open `type:pulse` issues and the commit history of `constitution/`.
3. **Constitution check.** Once the owner (`owner.github` in `limits.json`) has committed to
   `constitution/`, any later commit there by another author raises a `SECURITY` alert. With no owner
   commit at all, it records a warning that the constitution is not approved.
4. **Pulse check.** For each routine it compares the latest pulse with `max_silence_h` in
   `limits.json`. A silent OPS is a warning from `max_silence_h` and raises an `OUTAGE` alert after
   `alert_after_h`; a silent BIZ or FIN is a warning for OPS. If more than one routine is active and
   all of them are silent, it raises an `OUTAGE` alert. If a routine writes an `in-progress` pulse at
   the start of a shift and it stays longer than `max_shift_h`, the shift is reported as probably
   interrupted (the bundled routine prompts write only `ok`, `degraded` or `stop`).
5. **Revenue cap.** If `revenue.period_limit` is set, it warns at the lower `alert_thresholds` and
   raises a `CAP` alert at 95%.
6. Sends alerts through `tools/alarm.py`; if that fails, it opens an `urgent` incident issue.
7. Rewrites its own "Pulse: GUARDIAN" issue.

The guardian trusts GitHub author logins. Protect the owner account and the default branch (README,
"Limitations"; `SECURITY.md`).

## Limits

`constitution/limits.json` holds the numbers the rest of the kit reads. The main groups:

| Key | What it controls |
|---|---|
| `owner.github` | who may change `constitution/` (checked by the guardian) |
| `spending.without_desk` | spending allowed without a desk item (`state check` requires 0) |
| `spending.reserve_percent_of_balance` | share of the balance kept out of experiments |
| `revenue.*` | optional revenue cap, period length and alert thresholds |
| `alerts.*` | daily alert cap and repeat suppression |
| `desk.*` | default deadline, what no answer means, notice frequency |
| `tasks.lease_h`, `tasks.max_attempts` | lease length and attempts before a task is blocked |
| `power.*` | routine runs per day and subagents per shift |
| `routines.*` | schedule and silence thresholds per routine |
| `pace.*` | publications per channel per day, new repos per week |
| `approved_channels`, `approved_accounts` | where agents may publish and which accounts exist |

Agents may not raise limits; exceeding them needs a desk item (`constitution/CONSTITUTION.md`,
sections 3 and 7). `python3 tools/kit.py state check` validates the file on every shift.

## Where to go next

- Setup steps: README, "Setting up your own business".
- Failure modes and degradation order: `processes/RESILIENCE.md`.
- Changing prompts, processes and tools: `processes/CHANGE.md`.
- Platform behaviour and terms to verify: `docs/claude-platform.md`.
