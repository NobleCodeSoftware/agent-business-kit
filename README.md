# Agent Business Kit for Claude Code

A starter kit for **running a micro-business with AI agents on Claude Code routines** (scheduled cloud
sessions), while the human owner only decides and pays. It covers the business side, not the coding
workflow: an owner's desk for every human-only decision, a sales ledger, written stop conditions for
experiments, and pulses checked by an independent guardian. A constitution template, written processes,
small deterministic tools with tests and routine prompts hold it together, all in plain files and GitHub
issues.

> Status: early MVP (v0.1). It is a set of conventions and scripts, not a product with support.
> Read "Limitations" before you start.

**Built by AI, openly.** This kit is written and maintained by AI agents (Claude, working in Claude
Code); a human owner decides what ships. Code, documentation and release notes are produced that way,
and we say so rather than hide it.

## Demo

`kit.py desk check` decides whether a request to the owner is a complete yes/no package before an
agent is allowed to publish it. A real run on the two fictional examples shipped in `examples/`:

```console
$ python3 tools/kit.py desk check examples/desk-item.md
Item complete
$ python3 tools/kit.py desk check examples/desk-item-incomplete.md
Item INCOMPLETE - do not publish:
- due date 2020-01-15 has passed
- missing line **Urgency:** normal|urgent
- section "Why" is empty
- missing section "Risks and mitigation"
- missing section "Alternatives considered"
- missing section "If you decline or do not answer"
- missing section "Attachments"
- unfilled template field: <amount>
$ echo $?
1
```

The non-zero exit code lets a routine prompt or CI block the item instead of trusting the agent's
own judgement.

## Quick start (try it locally)

Requirements: Python 3.10 or newer (CI runs 3.10 and 3.12), git. Standard library only, nothing to
install. The tools run offline; Claude Code is needed only when you set up routines (next sections).

```bash
git clone https://github.com/NobleCodeSoftware/agent-business-kit.git
cd agent-business-kit
python3 -m unittest discover -s tools/tests
python3 tools/kit.py state check
python3 tools/kit.py desk check examples/desk-item.md
```

Expected: the tests end with `OK`, then `State OK` and `Item complete`.

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

## Setting up your own business (about 10 minutes, plus optional chat alerts)

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
5. **Turn on the guardian:** it is off by default, so the kit's own repo and fresh copies stay quiet.
   In Settings → Secrets and variables → Actions → Variables, add `GUARDIAN_ENABLED` = `true`. The
   `Guardian` workflow then runs hourly and creates the labels. Run it once by hand from the Actions tab
   to see its "Pulse: GUARDIAN" issue. In a fork, also enable workflows in the Actions tab.
6. **Create a permanent session** for OPS with your repo attached, then a **routine** that wakes it
   with the message from `routines/README.md`. Paste `routines/OPS.md` as the shift prompt after
   replacing the `[BRACKETED]` fields. Add BIZ and FIN the same way when OPS runs cleanly.
7. **(Optional) Alerts:** create a Discord bot and a private channel, then set `DISCORD_CHANNEL_ID`,
   `DISCORD_OWNER_ID` and the bot token (repo secrets for the guardian; environment secret or network
   secret for the agent session). Verify with `python3 tools/alarm.py test`. Without chat, the guardian
   falls back to `urgent` issues.
8. Create a first task issue (`processes/TASKS.md`) and watch the first shift: pulse, lease, result.

## Components

| Component | Purpose | Try it / where to start |
|---|---|---|
| `tools/kit.py` | Owner's desk completeness check (is the yes/no package complete?), sales ledger with a supplied exchange rate, optional revenue cap, forecast scoring (Brier) for experiments, pulses, STOP check, state validation, leases, intent/result records, guardian assessment | `python3 tools/kit.py --help`; e.g. `python3 tools/kit.py pulse --routine OPS --status ok --description "2 tasks done"` |
| `tools/alarm.py` | Owner alerts with dedupe and daily cap, batched desk notice, owner commands (`!stop`, `!start`, `!yes N`), plan B exit codes | `python3 tools/alarm.py --help`; after configuring Discord, `python3 tools/alarm.py test` |
| `tools/guardian.py` | Hourly watchdog for GitHub Actions, independent of the agents: pulses (is the business alive?), constitution integrity, revenue cap, plan B issues | `.github/workflows/guardian.yml`, enabled with the `GUARDIAN_ENABLED` variable (setup step 5) |
| `constitution/` | Constitution template and `limits.json` (owner, timezone, routines, revenue cap); owner-only | Fill the `[BRACKETED]` fields; `python3 tools/kit.py state check` validates `limits.json` |
| `processes/` | Desk, escalation, tasks with leases, resilience, change management, business development | Start with `processes/DESK.md` and `examples/desk-item.md` |
| `routines/` | Shift prompts for OPS, BIZ and FIN plus the permanent-session pattern | `routines/README.md` (wake message and example schedule) |
| `docs/` | Claude Code platform notes (routines, limits, terms) and suggested departments | `docs/claude-platform.md` |
| Tests and CI | Standard-library unit tests, a basic no-personal-data check, state and example validation | `python3 -m unittest discover -s tools/tests -v`; `.github/workflows/ci.yml` |

Experiments are run under written stop conditions (`processes/BUSINESS_DEVELOPMENT.md`): each one
states in advance when it is ended, so failures stay cheap.

Exit codes of `kit.py`: 0 OK, 1 validation error, 2 configuration or network error, 3 STOP active.

## Principles you inherit (and should keep)

- **Inbound only.** No cold outreach, no spam, no bought lists.
- **AI disclosure.** Never pretend to be human; label AI content where law or platform terms require.
- **No customers' personal data in agent sessions.** Keep customer data with the customer or the payment
  processor, not in the repo, issues or prompts. Consumer plans have no data processing agreement; a
  support channel that touches personal data needs commercial terms and a DPA.
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

## Roadmap and known gaps

Version 0.1 is the first public cut. Known gaps, in no promised order:

- no packaged release or installer: you copy the repository and edit files by hand;
- the emergency channel supports Discord only;
- no country-specific tax, invoicing or consumer-law modules (by design they would be optional);
- the permanent-session pattern and the platform notes depend on a research-preview feature and need
  re-checking as Claude Code routines change;
- the no-personal-data test catches only generic patterns unless you set `KIT_FORBIDDEN`.

Issues and pull requests that close these gaps without adding runtime dependencies are welcome.

## Repository layout

```
constitution/   template constitution + limits.json (owner-only)
processes/      DESK, ESCALATION, TASKS, RESILIENCE, CHANGE, BUSINESS_DEVELOPMENT
routines/       shift prompts (OPS, BIZ, FIN) + permanent-session pattern
docs/           platform notes, suggested departments
examples/       fictional desk items (one complete, one deliberately incomplete)
tools/          kit.py, alarm.py, guardian.py, labels.json, tests/
.github/        CI and guardian workflows
```

## Related

- [claude-pii-guard](https://github.com/NobleCodeSoftware/claude-pii-guard): a Claude Code plugin
  (a local PreToolUse hook, no network access) that checks file edits and `git commit`s for e-mail
  addresses, phone numbers, Polish PESEL numbers, IBANs, card numbers and your own private phrases,
  and by default blocks them (it can also ask or only warn). It is installed per machine; cloud
  sessions, including routines, load plugins differently, so check its README before relying on it
  there.

## Contributing, security, license

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
- Security: report vulnerabilities privately as described in [SECURITY.md](SECURITY.md); please do not
  open a public issue.
- License: [MIT](LICENSE).

## Trademarks

This is an independent community project. **Not affiliated with Anthropic**, and not endorsed or
sponsored by it. "Claude" and "Claude Code" are trademarks of Anthropic; "for Claude Code" is used only
descriptively, to say which tool the kit is meant to be used with. The project uses no Anthropic logos.

---
An experiment by NobleCode, run with the participation of AI.
