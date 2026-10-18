# Agent Business Kit for Claude Code

A starter kit for **running a micro-business with AI agents on Claude Code routines** (scheduled cloud
sessions), while the human owner only decides and pays. It covers the business side, not the coding
workflow: an owner's desk for every human-only decision, a sales ledger, written stop conditions for
experiments, and pulses checked by an independent guardian. A constitution template, written processes,
small deterministic tools with tests and routine prompts hold it together, all in plain files and GitHub
issues.

> Status: early MVP (v0.1). It is a set of conventions and scripts, not a product with support.
> Read "Limitations" before you start.

## The problem

Letting an AI agent "run a business" fails in boring ways, not dramatic ones:

- the agent forgets what happened yesterday, because every session starts fresh;
- two sessions grab the same job, or a crashed one leaves a job half done and nobody notices;
- nobody can tell whether the business is alive: a green job status does not mean work got done;
- money, accounts and legal commitments end up in places the owner never approved;
- the agent quietly rewrites its own rules.

This kit answers each one with a file or a script: state lives in git and issues, tasks carry leases,
liveness is measured by pulses and an outside guardian, a "desk" funnels every human-only decision into
a complete yes/no package, and the rules sit in a constitution the agents cannot edit.

## Architecture

```
                        OWNER (decides, pays, signs)
        STOP switch        ^  desk items (yes/no)       ^  emergency alerts
   (routines off / !stop)  |                            |  (closed list of codes)
                           |                            |
   +-----------------------+----------------------------+------------------+
   |                  repo + issues  =  the single source of state          |
   |  constitution/ (owner-only)   processes/   routines/   finance/ ...   |
   |  issues: tasks (leases) | desk | incidents | pulses | experiments     |
   +--^----------------^------------------^-----------------^---------------+
      |                |                  |                 |
  +---+----+      +----+----+        +----+----+      +-----+------+
  |  OPS   |      |  BIZ    |        |  FIN    |      |  GUARDIAN  |
  | shifts |      | experi- |        | ledger, |      | GitHub     |
  | + sub- |      | ments,  |        | audit   |      | Actions,   |
  | agents |      | forecast|        |         |      | hourly, no |
  +---+----+      +----+----+        +----+----+      | AI: pulses,|
      ^                ^                  ^           | constitu-  |
      |   permanent sessions, woken by scheduled      | tion guard,|
      +----------- routines (thin "new shift") -------+ cap, alerts|
                                                      +------------+
```

Key ideas:

1. **Constitution** (`constitution/CONSTITUTION.md`): overriding rules, decision rights, STOP switch, limits
   of self-improvement. Only the owner may change it; the guardian alerts otherwise.
2. **Desk** (`processes/DESK.md`): everything only a human can do, packaged so the answer is yes or no.
   No answer by the deadline means no.
3. **Tasks with leases** (`processes/TASKS.md`): issues claimed with an expiring lease; expired work
   returns to the queue; dead tasks are quarantined. External actions are recorded as intent and result,
   so retries are idempotent.
4. **Resilience** (`processes/RESILIENCE.md`): failure-mode table, circuit breakers, degradation order.
5. **Change management** and **business development with forecast calibration** (Brier score).
6. **Permanent department sessions** (`routines/README.md`, `docs/claude-platform.md`).

## Quickstart (about 10 minutes, plus optional chat alerts)

Prerequisites: a GitHub account, Python 3.10+, and a Claude plan that includes Claude Code routines.

1. **Create your repo from this one** (fork or "use as template"), clone it, and make it **private**
   while you set up (the kit is MIT, your business data is not).
2. **Edit `constitution/limits.json`:** set `owner.github` to your GitHub login, `timezone`,
   `base_currency`, and, if your legal form has a revenue ceiling, `revenue.period_limit`.
3. **Fill the constitution template** (`[BRACKETED]` fields). Commit it **as yourself**: the guardian
   treats any other author in `constitution/` as a security event.
4. **Check the tools:**
   ```bash
   python3 -m unittest discover -s tools/tests
   python3 tools/kit.py state check
   python3 tools/kit.py stop
   ```
   In CI of your own installation you can also forbid your own identifiers (names, domains, ids) without
   writing them into the repo: set `KIT_FORBIDDEN="phrase one,phrase two"` (comma-separated, from a CI
   secret) and the `TestNoPersonalData` test will fail if any phrase appears in the kit files.
5. **Turn on the guardian:** push; the `Guardian` workflow runs hourly and creates the labels. Run it
   once by hand from the Actions tab to see its "Pulse: GUARDIAN" issue.
6. **Create a permanent session** for OPS with your repo attached, then a **routine** that wakes it
   with the message from `routines/README.md`. Paste `routines/OPS.md` as the shift prompt after
   replacing the `[BRACKETED]` fields. Add BIZ and FIN the same way when OPS runs cleanly.
7. **(Optional) Alerts:** create a Discord bot and a private channel, then set `DISCORD_CHANNEL_ID`,
   `DISCORD_OWNER_ID` and the bot token (repo secrets for the guardian; environment secret or network
   secret for the agent session). Verify with `python3 tools/alarm.py test`. Without chat, the guardian
   falls back to `urgent` issues.
8. Create a first task issue (`processes/TASKS.md`) and watch the first shift: pulse, lease, result.

## Tools (standard library only)

| Tool | Purpose |
|---|---|
| `tools/kit.py` | Owner's desk completeness check (is the yes/no package complete?), sales ledger with a supplied exchange rate, optional revenue cap, forecast scoring (Brier) for experiments, pulses, STOP check, state validation, leases, intent/result records, guardian assessment |
| `tools/alarm.py` | Owner alerts with dedupe and daily cap, batched desk notice, owner commands (`!stop`, `!start`, `!yes N`), plan B exit codes |
| `tools/guardian.py` | Hourly watchdog for GitHub Actions, independent of the agents: pulses (is the business alive?), constitution integrity, revenue cap, plan B issues |

Experiments are run under written stop conditions (`processes/BUSINESS_DEVELOPMENT.md`): each one
states in advance when it is ended, so failures stay cheap.

Exit codes of `kit.py`: 0 OK, 1 validation error, 2 configuration or network error, 3 STOP active.

## Principles you inherit (and should keep)

- **Inbound only.** No cold outreach, no spam, no bought lists.
- **AI disclosure.** Never pretend to be human; label AI content where law or platform terms require.
- **No customers' personal data on consumer plans.** Keep customer data with the customer or the payment
  processor; a support channel that touches personal data needs commercial terms and a data processing
  agreement.
- **Money only through a human.** Agents have no card or bank access. Spending without a desk item is 0.
- **Terms of service.** Routines are a feature of your plan: do not share your account with anyone, and
  do not route customers through your personal subscription. Customer-facing AI needs an API key under
  commercial terms. Anthropic also says Pro/Max limits assume "ordinary, individual usage", so a
  heavy autonomous setup on a personal plan is a grey area. Verified 2026-10-15 (informal, not legal
  advice); read `docs/claude-platform.md` and the current official terms.

## Limitations (please read)

- **Not legal, tax or accounting advice.** The constitution and the ledger are templates. A lawyer or
  accountant must check them for your jurisdiction. The kit ships no country-specific tax logic; the
  ledger takes an exchange rate you supply, and the revenue cap is a generic percentage tracker.
- **Platform dependence.** Routines were still a research preview on 2026-10-15. Behaviour, limits
  and prices change; `docs/claude-platform.md` is a snapshot to verify, not a promise.
- **Usage limits are real.** Without usage credits, runs over the limit are rejected until the window
  resets; the kit assumes they are not retried (not documented). The guardian detects the silence; it
  cannot create capacity.
- **Prompt injection is mitigated, not solved.** Rules say external content is data, and QA reviews
  public output, but a determined attack on an agent with tool access remains a risk. Keep tool
  permissions narrow and secrets out of the agent's reach (network secrets, scoped tokens).
- **The guardian trusts GitHub author logins** for the constitution check. Protect the owner account
  (2FA) and use branch protection and required reviews so the check is defence in depth, not the only
  barrier.
- **Chat commands depend on the bot's Message Content Intent** and are read only at shift start.
  For an immediate stop, switch the routines off in the platform UI.
- **No revenue promise.** This is plumbing for running agents safely, not a business idea. Most
  experiments fail; the forecast and stop-condition process exists to make them fail cheaply.
- Tested with the standard-library test suite only; the Discord and `gh` integrations are exercised
  against fakes, not live services.

## Repository layout

```
constitution/   template constitution + limits.json (owner-only)
processes/      DESK, ESCALATION, TASKS, RESILIENCE, CHANGE, BUSINESS_DEVELOPMENT
routines/       shift prompts (OPS, BIZ, FIN) + permanent-session pattern
docs/           platform notes, suggested departments
examples/       a fictional desk item
tools/          kit.py, alarm.py, guardian.py, labels.json, tests/
.github/        CI and guardian workflows
```

## Contributing, security, license

See `CONTRIBUTING.md`, `SECURITY.md` and `LICENSE` (MIT).

This is an independent community project. "Claude" and "Claude Code" are products of their respective
owner; this kit is not affiliated with, endorsed or sponsored by them.

---
An experiment by NobleCode, run with the participation of AI.
