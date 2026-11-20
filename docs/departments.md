# Departments (suggested org chart)

Departments are roles that a shift plays, usually as subagents of the operations routine. The roles
below are an example, not a requirement: start with the minimum your business needs, merge or rename
roles freely, and add new ones only when there is work for them (`processes/CHANGE.md`). If you
rename a role, rename its routine key in `constitution/limits.json`, its prompt file in `routines/`
and its `dept:` label in `tools/labels.json` together. In those files, and in pulse titles and shift
ids, a role appears under its name in lower case (`operations`, `dept:operations`).

| Role | Mandate | Owns |
|---|---|---|
| Operations | Dispatcher: runs shifts, queue, leases, desk publication; platform health, incident runbooks, recreating routines, reverting bad changes | `routines/`, `processes/`, `tools/`, incident issues |
| Strategy | Experiments portfolio, forecasts, strategy memos | `knowledge/`, `decisions/` |
| Product | Builds products and tools; releases or sells them after quality review | `products/` |
| Marketing | Distribution: listing texts, launch posts on approved channels, inbound content | approved channels |
| Quality | Independent review of anything public, terms and legal checks, weekly sample of agent output | review verdicts |
| Finance | Ledger, costs, reserve, audit of reports | `finance/` |
| Support | Customer support (only after the first customer, and only with a channel that fits your privacy rules) | support log |

Rules that apply to every role: the constitution, the invariants in the routine prompts, the
two-keys rule (author is never the reviewer), and the file-ownership rule (one writer per state file).

## Product: definition of "ready to publish"

Works on mobile and desktop, tests pass, terms and privacy policy exist and AI use is disclosed where
required, a product description for Marketing exists, and Quality has approved.
