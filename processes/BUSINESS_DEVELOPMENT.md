# Business development (BIZ): process

BIZ answers three questions: **what works, what does not, and what do we do next.** It manages a
portfolio of experiments like an investor. Each experiment is a bet with a defined stake (money and
compute), a hypothesis and a stop condition fixed in advance.

## Rhythm

| When | What | Output |
|---|---|---|
| Every morning (BIZ routine) | Signal review: channel metrics, deviations, new opportunities from watched sources | note in `knowledge/signals/YYYY-MM-DD.md`, experiment cards updated |
| Monday (full mode) | Portfolio review: a decision for each experiment (stop, continue, scale, pivot), re-rank the opportunity backlog, 1-3 new proposals, red-team critique | decision records, weekly report for the owner |
| Last day of the month | Strategy memo: P&L, unit economics, lessons, next month's plan. Investment memo if the data justifies it | `decisions/memo-YYYY-MM.md`, a desk item when asking for capital |

## Experiment card (issue `type:experiment`)

```markdown
# EXP-<n>: <name>
## Hypothesis
If we <do X> for <whom> in <channel>, then <measurable effect> within <time>, because <reasoning>.
## Success metric
Primary: <e.g. first sale / visit-to-purchase conversion >= 1%>   Secondary: <views, favourites, CTR>
## Stop condition (fixed in advance)
<e.g. < 150 views after 10 days, or 0 sales after 21 days with >= 600 views>
## Stake
Money: <amount, from desk item #...>   Compute: <shifts per week>   Time: <until YYYY-MM-DD>
## Forecast
P(first sale by <date>) = <x%>   Expected 30-day revenue: <pessimistic/base/optimistic>
## Log
<dated entries: what was done, what was measured>
## Final decision
<stopped/scaled/pivoted> — <reasoning>, link to the decision record
```

## Opportunity scoring rubric

Score each opportunity 1-5 on every criterion; the result is the weighted sum.

| Criterion | Weight |
|---|---|
| Time to first revenue | 3 |
| Evidence of demand (data, not intuition) | 3 |
| Fit with autonomy (API, git, no manual owner work) | 2 |
| Legal, platform-terms and privacy risk (inverted) | 2 |
| Capital needed (inverted) | 1 |
| Competition (inverted) | 1 |
| Fit with AI strengths | 1 |
| Scalability | 1 |

An opportunity that breaks the constitution (needs cold outreach, processing customers' personal data
or pretending to be human) is out regardless of its score.

## Red team

Before every "scale" or "new experiment" decision BIZ launches a separate subagent whose only job is to
find reasons **not** to do it: run a pre-mortem, check the data, expose hidden costs and platform-terms
risks. The response to the critique goes into the decision record. A decision without critique is
considered not thought through.

## Calibration (data-driven self-improvement)

Every forecast (e.g. "P(first sale within 21 days) = 35%") is logged in `knowledge/calibration.csv`
(columns: `date,experiment,event,probability,deadline,outcome`). When the deadline passes, fill
`outcome` with 1 or 0. Each month BIZ runs `python3 tools/kit.py brier` and checks whether the business
is systematically over-optimistic (mean forecast above base rate). Findings correct future forecasts and
stop thresholds. This is how the business learns from its own results rather than from hunches.

## Decision record (`decisions/DR-<n>-<slug>.md`)

```markdown
# DR-<n>: <decision>
Date: <YYYY-MM-DD>   Department: <...>   Status: accepted | superseded by DR-<n>
## Context
## Options considered (scored with the rubric)
## Decision and rationale
## Red-team critique and response
## How we will know it was wrong (signal to revisit)
```

## Investment memo (asking the owner for capital)

The owner invests only when data convinces them. The memo goes to the desk and contains:

1. **Thesis:** what works, with evidence (sales, conversions, trend). No data, no memo.
2. **Ask:** amount, what exactly for, in which tranches.
3. **Milestones:** what must happen to release the next tranche.
4. **Economics:** acquisition cost, margin, break-even, sensitivity to assumptions.
5. **Risks and stop-loss:** at what result we stop and the maximum possible loss.
6. **Alternative without investment:** what we do if the owner declines.
