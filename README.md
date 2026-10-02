# evalgate

A quality gate for LLM and agent output. Point it at a golden set and the
function that answers, and it tells CI whether the change you are about to
merge made the system worse.

Prompt changes do not fail loudly. A reworded instruction, a new model
version, a different retrieval setting — nothing throws, nothing 500s, and the
answers quietly get worse in ways a diff cannot show you. evalgate turns that
into a build failure.

```
pip install evalgate
evalgate run -c evalgate.yaml
```

Exit code 0 when the gate passes, 1 when it does not. That is the whole
integration surface.

## What it checks

| check | what it catches |
| --- | --- |
| `schema` | a missing field, a string where a number belongs, an invented enum value |
| `grounding` | a citation the context never contained, and claims nothing supports |
| `contains` | required and forbidden phrases, and regex patterns, per case |
| `numeric` | numeric fields drifting outside a tolerance |

`grounding` is the one that earns its keep. It separates two failures that get
lumped together: a **fabricated citation** — a quote attributed to the source
that the source never said — fails the case outright, because that is the
dangerous one. An **unsupported claim** — a sentence no citation backs — is
scored, because some connective prose is normal.

## A real run

The repo ships a worked example: a small retrieval-backed support bot, eight
golden cases, and a schema.

```console
$ evalgate run -c examples/support_bot/evalgate.yaml
evalgate: support-bot

  [PASS] returns-window  (0ms)
  [PASS] refund-timing  (0ms)
  ...
  [PASS] empty-context-abstain  (0ms)

  8/8 cases passed (100.0%)
    contains     100.0%
    grounding    100.0%
    schema       100.0%

  gate: PASSED
```

Now make the bot behave the way they do on a bad day — confident, over-broad,
quoting a policy that does not exist:

```console
$ SUPPORT_BOT_SLOPPY=1 evalgate run -c examples/support_bot/evalgate.yaml
  [FAIL] returns-window  (0ms)
         contains: should not say 'no exceptions'
         grounding: 1 citation(s) do not appear in the context:
                    'All regions are covered with no exceptions.'
  ...
  0/8 cases passed (0.0%)
    contains     62.5%
    grounding    0.0%
    schema       100.0%

  regression: returns-window / grounding
  ...

  gate: FAILED
    - pass rate 0.0% is below the required 100.0%
    - check 'grounding' at 0.0% is below its floor of 100.0%
    - 11 regression(s) against the baseline, max allowed 0

$ echo $?
1
```

Note what the schema check says: 100%. The output was perfectly well-formed
the whole time. Structural validation alone would have let this merge.

## Configuration

```yaml
name: support-bot
dataset: golden.jsonl

system:
  type: python          # or: command
  target: system:answer # module:callable, or an argv string for `command`
  timeout_s: 30

checks:
  - type: schema
    schema: schema.json
  - type: contains
    field: answer
  - type: grounding
    answer_field: answer
    citations_field: citations
    context_field: context
    min_support: 0.8    # share of claims that must be backed by a citation
    min_overlap: 0.4    # token overlap before a citation counts as backing one

gate:
  min_pass_rate: 1.0
  max_regressions: 0
  per_check:
    grounding: 1.0

baseline: baseline.json
```

A golden case is one JSON object per line:

```json
{"id": "returns-window", "tags": ["policy"],
 "input": {"question": "How long do I have to return an item?",
           "context": "Returns are accepted within 30 days of delivery."},
 "expect": {"must_contain": ["30 days"], "must_not_contain": ["90 days"]}}
```

The system under test is anything that takes the `input` object and returns a
JSON object — a Python callable, or a command that reads stdin and writes
stdout, which covers services in any language.

## Regressions, not just scores

A falling average is easy to miss once a suite is large enough. What you want
to block is the specific case that used to pass and now does not.

```bash
evalgate baseline -c evalgate.yaml       # record the current outcomes
evalgate run -c evalgate.yaml            # compare against them
evalgate run -c evalgate.yaml --update-baseline
```

`max_regressions: 0` fails the build on the first one, and the report names
the case and the check, so the failure is actionable rather than a number
going down.

## In CI

```yaml
- run: pip install evalgate
- run: evalgate run -c evals/evalgate.yaml --markdown eval.md --junit eval.xml
- if: always()
  run: cat eval.md >> "$GITHUB_STEP_SUMMARY"
```

`--junit` feeds the usual test reporters. `--markdown` is written to be pasted
into a pull request comment. `--json` has everything, including per-check
evidence for each case.

Run a subset while iterating:

```bash
evalgate run --only returns-window --only warranty   # case ids or tags
```

## Adding a check

```python
from evalgate.checks import CheckResult, register

@register("no_pii")
class NoPiiCheck:
    name = "no_pii"

    def __init__(self, root=None, patterns=None, **_):
        self.patterns = patterns or [r"\b\d{3}-\d{2}-\d{4}\b"]

    def run(self, case, output):
        hits = [p for p in self.patterns if re.search(p, output.get("answer", ""))]
        return CheckResult(self.name, passed=not hits, score=0.0 if hits else 1.0,
                           detail=f"{len(hits)} pattern(s) matched")
```

Import the module anywhere before the run and `type: no_pii` works in the
config. `evalgate checks` lists what is registered.

## Design notes

- **Deterministic by default.** Nothing here calls a model. The checks are
  mechanical, so the gate is reproducible and runs offline in CI for free. An
  LLM judge is a check you can add, not a dependency you inherit.
- **Scores are secondary.** The gate's job is a verdict with a reason attached.
- **A crashing system fails one case, not the run.** The suite finishes and
  tells you which case errored.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check . && mypy evalgate
```

MIT licensed.
