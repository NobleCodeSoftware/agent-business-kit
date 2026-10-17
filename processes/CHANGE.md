# Change management and self-improvement

## What agents may change

Department cards, routine prompts (`routines/`), processes (`processes/`), tools (`tools/`), products
(`products/` or your own repos) and knowledge (`knowledge/`, `decisions/`). Never `constitution/`
(constitution, section 7).

## Change path

1. **Rationale:** what does not work (data, incident, lesson) and what effect the change should have.
2. **PR** from the session branch to the default branch. The description states the rationale, the risk
   and the rollback plan.
3. **Tests:** every change in `tools/` passes `python3 -m unittest discover -s tools/tests` (locally
   and in CI).
4. **QA review** by an agent other than the author. For changes to routine prompts QA additionally
   checks that the minimal invariants remain (STOP, pulse, alert, no external actions on corrupted
   state).
5. **Merge** by OPS (processes, prompts, tools) or by the file's owner (e.g. FIN for `finance/`).
6. **Measurement:** after a week BIZ or IT checks whether the change had an effect. If not, revert.

## Weekly retrospective (part of the BIZ Monday review)

- What went well, what went badly, what we learned -> `knowledge/lessons.md`.
- Which processes or prompts slowed work or produced errors -> tasks for the file owners.
- Were the forecasts accurate -> calibration (`processes/BUSINESS_DEVELOPMENT.md`).

## Structure grows with revenue

A new department, routine or higher frequency appears only when there is work for it confirmed by data
(e.g. Customer Support after the first customer). Structure without work burns subscription limit and
creates noise. OPS may change the schedule within `limits.json`. Anything above goes to the desk.
