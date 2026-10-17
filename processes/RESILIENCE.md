# Resilience

Requirement: **a mistake by one agent must not block the whole business.** This document describes how
we ensure it, technically and commercially.

## Principles

1. **Stateless shifts, state outside.** No session holds knowledge the business cannot run without.
   State lives in the repo (files) and in issues (tasks, desk, incidents, pulses). Any shift can be
   killed at any moment and the next one picks up the work.
2. **Independent failure domains.** Three separate routines (OPS, BIZ, FIN) watch each other. The
   guardian runs outside Claude (GitHub Actions), so it notices a failure even when the subscription
   limit is exhausted. Alerts have a plan B (chat -> `urgent` issue).
3. **Bulkheads.** Departments and tasks are isolated. A blocked task blocks only itself. A failing
   department is marked `degraded`; the rest keep working.
4. **Leases instead of locks.** A claimed task has a lease with an expiry (`tasks.lease_h`). When it
   expires the task returns to the queue. After `tasks.max_attempts` failed attempts it lands in
   `state:blocked` (dead-letter queue) with an incident. See `TASKS.md`.
5. **Idempotent external actions.** Before an external action (publishing, sending, listing a product)
   the agent records an intent with an id; afterwards the result. A repeated shift first checks whether
   the action already happened, so there are no double publications.
6. **Circuit breakers.** Three consecutive failures of the same action on the same channel switch that
   channel off (`channel:paused`) until IT or OPS analyses it. Pace limits in `limits.json` (e.g.
   publications per day) protect against a loop that spams.
7. **Two keys.** Nothing goes public without QA review by an agent other than the author. Nothing
   financial happens without the owner.
8. **Safe by default.** Missing data, contradictory data, corrupted state or legal uncertainty mean no
   external action. The agent records the problem and moves on.
9. **One writer.** Every state file has one owning department. Others file a task or a PR to the owner.
   Log files are append-only.
10. **Degradation by priority.** When capacity (subscription limit) or time runs short, the order is:
    (1) security and legal, (2) customers and statutory deadlines, (3) revenue tasks, (4) growth,
    (5) research.
11. **Mutual oversight.** OPS checks the BIZ and FIN pulses. FIN audits OPS reports against source data.
    The guardian checks everyone and ensures nobody but the owner changes `constitution/`.
12. **Reversibility.** Everything is in git. A change after which things start failing is undone with
    `git revert` without waiting for analysis. Analysis comes later.

## Business resilience

- **Channel diversification:** after three months no channel brings more than 70% of revenue. Before
  that, every experiment has a backup channel.
- **Backups:** product files, offer texts, prices and images are in the repo. A platform ban does not
  take the product away.
- **Reserve:** 30% of the balance (`spending.reserve_percent_of_balance`) is not spent on experiments;
  it covers refunds, renewals and fixed costs.
- **Terms compliance as protection:** QA reads a channel's terms before the first publication and
  monthly. A ban is the biggest risk for a faceless business.
- **No dependence on the owner in operations:** the owner is needed for decisions and transactions,
  not for daily work. Their absence slows spending, it does not stop the business.

## Failure modes (FMEA)

| # | Failure | Detection | Automatic reaction | Repair |
|---|---|---|---|---|
| 1 | Shift dies mid-task | lease expires | task returns to the queue | next shift, idempotency |
| 2 | Routine stops launching | guardian: stale pulse | `OUTAGE` alert for OPS after `alert_after_h`; warning for BIZ and FIN | IT or owner checks the routine |
| 3 | Subscription limit exhausted | session errors, no pulse | degradation by priority, low-priority shifts drop out | wait for the limit window |
| 4 | Bad change to instructions or tools | CI tests, failed shifts after rollout | routine start prompts contain minimal invariants | IT runs `git revert`, then post-mortem |
| 5 | Wrong product or content (hallucination) | QA review, complaints | no publication without QA | fix, post-mortem, lesson |
| 6 | Manipulation via external content (prompt injection) | QA, unusual actions in the log | refuse to execute, `SECURITY` incident on attempted exfiltration | analysis, harden the rules |
| 7 | Account blocked on a platform | API error, platform email | `channel:paused`, `ACCOUNT` alert | owner appeals, backup channel |
| 8 | Payouts withheld | FIN: balance mismatch | reserve covers costs | desk: action toward the platform |
| 9 | Owner does not respond | desk deadline | default decline, work continues | - |
| 10 | Chat service down | exit code 2 from `alarm.py` | `urgent` issue | owner checks secrets |
| 11 | GitHub unavailable | tool errors | the shift ends without external actions | next shift |
| 12 | Corrupted state file | `kit.py state check` | writes to that file halted, incident | restore from git history |
| 13 | Two shifts at once | PR or lease conflict | staggered schedules, retry after rebase | - |
| 14 | Revenue ceiling approaching | FIN, thresholds in `limits.json` | BIZ slows sales at 85% | desk: change legal form |
| 15 | Action loop (spam) | pace limits | hard limit in tools and `limits.json` | analysis and fix |
| 16 | A department keeps failing | 3 failed shifts in a row | department `degraded`, others continue | IT and OPS: post-mortem |
| 17 | Model behaviour drift | weekly QA sample | - | adjust prompts and processes |
