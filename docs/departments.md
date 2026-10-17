# Departments (suggested org chart)

Departments are roles that a shift plays, usually as subagents of OPS. Start with the minimum your
business needs and add roles only when there is work for them (`processes/CHANGE.md`).

| Dept | Mandate | Owns |
|---|---|---|
| OPS | Dispatcher: runs shifts, queue, leases, desk publication, health checks | `routines/`, `processes/`, `tools/` |
| BIZ | Experiments portfolio, forecasts, strategy memos | `knowledge/`, `decisions/` |
| BLD | Builds products and tools; releases or sells them after QA | `products/` |
| GRW | Distribution: listing texts, launch posts on approved channels, inbound content | approved channels |
| QA | Independent review of anything public, terms and legal checks, weekly sample of agent output | review verdicts |
| FIN | Ledger, costs, reserve, audit of reports | `finance/` |
| SUP | Customer support (only after the first customer, and only with a channel that fits your privacy rules) | support log |
| IT | Platform health, incident runbooks, recreating sessions, reverting bad changes | incident issues |

Rules that apply to every department: the constitution, the invariants in the routine prompts, the
two-keys rule (author is never the reviewer), and the file-ownership rule (one writer per state file).

## BLD: definition of "ready to publish"

Works on mobile and desktop, tests pass, terms and privacy policy exist and AI use is disclosed where
required, a product description for GRW exists, and QA has approved.
