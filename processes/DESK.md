# The owner's desk

The desk collects everything only the owner can do: payments, contracts, terms acceptance, account
creation, identity verification, refunds and changes to `constitution/`. Principle: **the owner
should not have to search, calculate or write anything.** They get a ready package and decide yes or no.

## Where the desk is

- Issues labelled `type:desk`. Filter: `is:open label:type:desk`.
- OPS announces new items in one batched chat message, at most once a day.
- Urgent items (deadline under 48 h) go out immediately as an alert (`processes/ESCALATION.md`).

## How the owner answers

In an issue comment or in chat (`!yes 12`, `!no 12`):

- `/yes`: approved; the owner performs the steps and adds `done` when finished.
- `/no`: declined (a reason is welcome).
- `/question ...`: answered by the department that prepared the item.

No answer by the deadline means decline. OPS closes the item with the label `result:expired`.

## Who prepares an item, and when

1. The department that needs the decision drafts it from the template below.
2. For spending, FIN checks the amount, tax effects and available funds.
3. For contracts, terms and accounts, QA reviews the document and lists key points, risks and
   prohibitions (e.g. a ban on automation) in the item.
4. OPS checks completeness with `python3 tools/kit.py desk check <file>` and publishes the issue.
5. After the owner acts, the department verifies the outcome, adds it to the issue and closes it.

## Item template

```markdown
# [DESK] <action> — <amount or "0"> — due YYYY-MM-DD

**Urgency:** normal | urgent    **Department:** <BIZ/OPS/...>    **Related:** <experiment / task>

## What exactly you need to do
1. <step with a ready link>
2. <data to paste, in code blocks>
3. <how to confirm it is done>

## Why
<business goal in 2-4 sentences, link to the experiment or strategy>

## Cost and return
- Cost: <gross amount, one-off or monthly, from which funds>
- Expected effect: <numbers, with assumptions>
- Payback / break-even: <when, under which assumptions>

## Risks and mitigation
- <risk> -> <mitigation>

## Alternatives considered
- <alternative> — <why not>

## Recommendation
<YES/NO>, confidence <low/medium/high>. <1-2 sentences of reasoning>

## If you decline or do not answer
<what we do instead>

## Attachments
<contract or terms with key points extracted, screenshots, calculations>
```

All `##` sections are mandatory. `kit.py desk check` rejects a draft that lacks any of them, still
contains `<placeholder>` fields, or has a due date in the past. A complete fictional example is in
`examples/desk-item.md`.
