# Routines per department

## The pattern

Every role that runs on a schedule (in the example org chart: operations, strategy, finance) gets its
own **routine** with the business repository attached in the routine itself. Each scheduled run starts
a **fresh cloud session** with a fresh clone of the repositories attached to the routine. Nothing
carries over between runs: the session **does not rely on memory**, and business state is in the repo
and in issues.

The real instructions live in the repo (`routines/<role>.md`) and change through PRs with quality
review. Replace the `[BRACKETED]` fields in your copy before the first run. The routine's prompt can
then be either:

- **the full file** (`routines/operations.md` etc.). Its invariants then apply even if the repo
  cannot be read. The prompt in the platform UI must stay identical to the file: changing a prompt
  means changing the file (PR with quality review) and then updating the routine.
- **a short prompt** that tells the session to read the file and execute it. The file is then the only
  copy, so updating it is enough, but if the repo is unavailable the session has no instructions.

Example short prompt:

> New shift. Read `routines/operations.md` from the default branch of the attached business
> repository and execute it in full.

## Hygiene

- If a routine keeps producing no pulse despite runs, Operations checks the routine (attached
  repositories, connectors, environment, prompt) and fixes or recreates it. When the silent routine
  is operations itself, the owner does this.
- Keep a private inventory of routine ids outside the repository.

## Schedule

Use UTC so that daylight-saving changes do not shift windows. If the account is also used interactively,
schedule routines so they do not compete with that usage. The defaults in `constitution/limits.json`:

| Routine | Prompt file | Example cron (UTC) | Roles (`docs/departments.md`) |
|---|---|---|---|
| operations | `operations.md` | `0 0,6,12,18 * * *` | Operations + subagents Product, Marketing, Quality, Support (at most `max_subagents_per_shift` per shift) |
| strategy | `strategy.md` | `30 7 * * *` (Monday: full mode) | Strategy |
| finance | `finance.md` | `30 20 * * *` | Finance |

Operations may change the schedule within the bounds of `constitution/limits.json`.
