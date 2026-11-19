# Routines per department

## The pattern

Every department that runs on a schedule (OPS, BIZ, FIN) gets its own **routine** with the business
repository attached in the routine itself. Each scheduled run starts a **fresh cloud session** with a
fresh clone of the repositories attached to the routine. Nothing carries over between runs: the session
**does not rely on memory**, and business state is in the repo and in issues.

The real instructions live in the repo (`routines/<DEPT>.md`) and change through PRs with QA review.
Replace the `[BRACKETED]` fields in your copy before the first run. The routine's prompt can then be
either:

- **the full file** (`routines/OPS.md` etc.). Its invariants then apply even if the repo cannot be
  read. The prompt in the platform UI must stay identical to the file: changing a prompt means changing
  the file (PR with QA review) and then updating the routine.
- **a short prompt** that tells the session to read the file and execute it. The file is then the only
  copy, so updating it is enough, but if the repo is unavailable the session has no instructions.

Example short prompt:

> New shift. Read `routines/OPS.md` from the default branch of the attached business repository and
> execute it in full.

## Hygiene

- If a routine keeps producing no pulse despite runs, IT checks the routine (attached repositories,
  connectors, environment, prompt) and fixes or recreates it.
- Keep a private inventory of routine ids outside the repository.

## Schedule

Use UTC so that daylight-saving changes do not shift windows. If the account is also used interactively,
schedule routines so they do not compete with that usage. The defaults in `constitution/limits.json`:

| Routine | Prompt file | Example cron (UTC) | Department |
|---|---|---|---|
| OPS | `OPS.md` | `0 0,6,12,18 * * *` | OPS + subagents BLD, GRW, QA, SUP, IT |
| BIZ | `BIZ.md` | `30 7 * * *` (Monday: full mode) | BIZ |
| FIN | `FIN.md` | `30 20 * * *` | FIN |

OPS may change the schedule within the bounds of `constitution/limits.json`.
