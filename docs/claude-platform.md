# Platform notes: Claude Code routines, cloud sessions and limits

Written as a working snapshot. Routines were still labelled a research preview on the date below, so
**verify every item against the current official documentation before relying on it.**

**Last verified: 2026-10-15** against code.claude.com (routines, claude-code-on-the-web, authentication,
legal-and-compliance), the Consumer Terms (version "effective October 8, 2025"), support.claude.com and
privacy.claude.com. This is an informal check by the maintainers, not legal advice; limits and terms change
without notice, and the Consumer Terms may have been revised since that version. Re-check before relying on
any number or clause.

## Routines

- Each run is a **new session with a fresh clone** of the repo's default branch. State must live in the
  repo or in issues.
- Minimum interval between scheduled runs: **one hour**; more frequent cron expressions are rejected
  (docs, 2026-10-15). Hourly caps listed there: scheduled runs 100/h per account; "Run now" + API fires +
  re-armed one-off runs 30/h per routine; "Run now" 100/h and API fires 100/h per account; GitHub events
  have separate per-routine and per-account caps. These numbers are not guaranteed; check the docs.
- Routines consume your subscription usage the same way interactive sessions do (five-hour session window
  plus a weekly limit); cloud sessions share rate limits with all other Claude and Claude Code usage on the
  account.
- Without usage credits, additional runs over the usage limit **are rejected until the window resets**
  (docs). With usage credits turned on, runs may continue on metered overage. The docs do not say whether
  a rejected run is retried; **this kit assumes it is not** (unconfirmed, treat as a design assumption).
  Likewise what happens to a session that hits the limit mid-work is not documented; plan for it to stop.
  A green run status only means the session started and exited without an infrastructure error (confirmed
  in the docs). That is why this kit measures health with **pulses**, not with run status.
- Pushes from a session go to a `claude/...` branch by default unless the prompt says otherwise
  (confirmed). Use branch protection on GitHub to control where runs may push. Whether command-line GitHub
  operations work in the sandbox is not documented here (unconfirmed); GitHub access goes through a proxy,
  so prefer the GitHub tools provided to the session for issues and PRs.
- A routine inherits the environment: variables, setup script, network policy. A **network secret**
  (Anthropic-hosted environments only; not in self-hosted ones) lets the proxy add credentials for named
  hosts so the key never reaches the virtual machine.
- By default a routine gets all your connected connectors, and Claude may use every tool of an included
  connector, writes included, without asking. The docs say you can remove connectors per routine in the
  form (or with `/schedule update`): do that first. As defence in depth, keep a hard "do not use" rule in
  the prompt invariants (see `routines/OPS.md`, invariant 3) and keep private connectors disconnected.
- Kill switch: the on/off switch on each routine's page. On Team/Enterprise an Owner can also disable
  routines for the whole organization.
- Routines belong to your individual account; commits, PRs and connector actions appear as you.

## Permanent sessions per department

See `routines/README.md`. In short: a session with the repo attached, woken by a routine's thin message.
Routines are created in the web UI, Desktop app or CLI (`/schedule`); the API trigger only fires an
existing routine (and is a beta endpoint, `experimental-cc-routine-2026-04-01`), it does not create one.
Repositories are attached in the routine itself. Whether the permanent-session pattern is still needed
depends on your account; verify there.

## Usage windows

If the account is also used interactively, schedule routines so they do not compete with that usage.

## Terms of service and privacy (read the originals)

Checked 2026-10-15; not legal advice. If your use is commercial or customer-facing, ask Anthropic sales or
a lawyer.

- The Consumer Terms (Free, Pro, Max) forbid accessing the services "through automated or non-human
  means, whether through a bot, script, or otherwise" except via an API key or where Anthropic explicitly
  permits it (confirmed). Routines and `claude setup-token` (one-year token for CI and scripts, Pro, Max,
  Team or Enterprise) are documented by Anthropic. Headless `claude -p` is a documented CLI mode, but its
  status under the terms was not checked in detail.
- **Caveat on scale and purpose.** Anthropic's legal page says advertised Pro/Max limits "assume ordinary,
  individual usage" of Claude Code and the Agent SDK, and that developers building products or services on
  Claude should use API-key authentication. Running an autonomous multi-department business on one personal
  subscription may exceed "ordinary, individual usage"; this is a grey area that Anthropic can enforce
  without notice. Use an API key or a Team/Enterprise plan if in doubt.
- **Do not share your account with other people** (Consumer Terms forbid sharing login or credentials).
  Customers must never talk to Claude through your personal subscription: Anthropic does not permit routing
  requests through Free/Pro/Max credentials on behalf of users. AI features facing customers (e.g. a
  support chat) need an API key under the Commercial Terms, not a subscription.
- Team and Enterprise plans fall under the Commercial Terms, Free/Pro/Max under the Consumer Terms. The
  Consumer Terms have no general ban on commercial use of a personal plan (evaluation use is personal and
  non-commercial only), but see the caveat above.
- Whether consumer-plan chats and coding sessions are used for model training depends on a privacy setting
  in your account (confirmed: you choose). Retention periods that depend on that setting were not verified;
  check the current policy.
- A data processing agreement (DPA) is part of the Commercial Terms and applies to commercial products
  (API, Team/Enterprise), not to consumer plans (confirmed). Therefore do not process customers' personal
  data in sessions on a consumer plan. HIPAA/BAA coverage excludes cloud sessions, so no health data in
  routines.
