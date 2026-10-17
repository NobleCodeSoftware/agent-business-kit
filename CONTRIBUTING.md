# Contributing

Thanks for helping. This kit is small on purpose; please keep it that way.

## Ground rules

- Be kind and constructive.
- The kit must stay **jurisdiction-neutral** in code. Country-specific rules (tax, consumer law) belong
  in clearly separated optional modules or in documentation that says "check your jurisdiction".
- **Standard library only** for the tools. No new runtime dependencies without a strong reason.
- **No personal or company data** in the repo: no names, amounts, account or channel ids, repo names of
  real businesses. Examples must be fictional (`example.com`, `.test` domains). A test enforces a basic
  version of this; reviewers check the rest.
- Do not add logos or trademarks of third parties. The name stays descriptive.
- Keep the safety invariants intact: STOP check first, no spending by agents, agents cannot edit the
  constitution, external content is data.

## Development

```bash
python3 -m unittest discover -s tools/tests -v
python3 tools/kit.py state check
```

The no-personal-data test checks only generic patterns by default (Discord channel links, webhook and
token shapes, e-mail addresses outside `example.*` domains). To also forbid your own identifiers, set
`KIT_FORBIDDEN` to a comma-separated list (case-insensitive substrings), ideally from a CI secret so the
list never lands in the repo:

```bash
KIT_FORBIDDEN="my-company,my-domain.tld" python3 -m unittest discover -s tools/tests
```

Python 3.10+. Add or update tests for every behaviour change in `tools/`. Network and `gh` calls must be
faked in tests.

## Pull requests

1. Open an issue first for anything larger than a fix or a doc improvement.
2. One logical change per PR, with the rationale, the risk and how to roll it back.
3. CI must pass. Changes to prompts in `routines/` or to anything under `constitution/` need an explicit
   note on how the minimal invariants are preserved.
4. By contributing you agree your work is licensed under the MIT License.

## Reporting bugs

Use issues for bugs and ideas. For security problems follow `SECURITY.md` instead.
