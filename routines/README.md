# Routines and permanent department sessions

## The pattern

Every department that runs on a schedule (OPS, BIZ, FIN) gets a **permanent session** in the cloud with
the business repository attached and its own branch (for example `ops/shift`, `biz/shift`, `fin/shift`).
A scheduled routine **wakes that session** with a thin message such as "new shift".

Why: a routine created through an API may start a fresh session **without the repo and without GitHub
tools**; adding a repo to such a routine may be possible only by hand in the web UI. A permanent session
created with a repo source has the repo, the GitHub tools (issues, PRs, merging) and session management,
so it works without the owner.

The wake message is deliberately thin. It tells the session to sync its branch, re-read
`routines/<DEPT>.md` from scratch and execute it fully. The real instructions live in the repo and change
through PRs with QA review. The session **does not rely on memory**: business state is in the repo and in
issues.

Example wake message:

> New shift. Sync your branch with the default branch, re-read `routines/OPS.md` and execute it in full.

## Hygiene

- Session context grows; the platform compacts it on its own.
- A session that stopped working (no pulse despite routine runs) is recreated by IT: create a new
  permanent session from the same repo, point the routine at it, and let the old one be archived.
- Keep a private inventory of session and routine ids outside the repository.

## Schedule

Use UTC so that daylight-saving changes do not shift windows. If the account is also used interactively,
schedule routines so they do not compete with that usage. The defaults in `constitution/limits.json`:

| Routine | Prompt file | Example cron (UTC) | Department |
|---|---|---|---|
| OPS | `OPS.md` | `0 0,6,12,18 * * *` | OPS + subagents BLD, GRW, QA, SUP, IT |
| BIZ | `BIZ.md` | `30 7 * * *` (Monday: full mode) | BIZ |
| FIN | `FIN.md` | `30 20 * * *` | FIN |

The prompt in the platform UI must be identical to the file. OPS reports any mismatch. Changing a prompt
means changing the file (PR with QA review) and then updating the routine. OPS may change the schedule
within the bounds of `constitution/limits.json`.
