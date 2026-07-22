# ADR 0004: No LLM question-answering layer

**Status**: accepted · **Date**: 2026-07-22

## Context

The dashboard answers a fixed set of questions well. The natural next feature looked like a
local LLM — free, offline, no API keys — letting a user type free-form questions and have
them answered from the database, the marts, or the model registry. It fits the zero-cost
constraint (Ollama on the host, a 7B model at Q4 ≈ 5 GB alongside a ~2.5 GB Docker stack on
16 GB) and is an obvious portfolio talking point.

Scoping it produced the opposite conclusion.

## Decision

**Do not add one.** Two designs were considered and both fail for the same underlying reason.

- **Text-to-SQL is rejected outright.** A small local model writing SQL over 8 tables and 9
  marts will omit `WHERE variant = 'daily'` and silently sum both paper books, or pick the
  wrong join. Failures return *a* number rather than an error, so they are invisible. Worse,
  it bypasses every guardrail by construction: asked for the live Sharpe it computes −35.25
  from two rows — precisely the figure the dashboard deliberately withholds.
- **Tool-calling over the existing endpoints is safe but redundant.** Making it safe means
  forbidding arithmetic and raw queries, and withholding unreliable statistics from the
  payload so the model cannot repeat them. What remains is a natural-language index over ~18
  read-only endpoints whose answers are *already written out in English on the page*.

The deciding fact: **the summarization layer already exists and is strictly better.** The
`verdict()` functions in `AlphaBetaCard` and `BookComparisonCard`, and the withholding notice
in `TrackRecordCard`, do exactly the "explain these numbers in plain English" job an LLM is
usually reached for. They are deterministic, unit-tested, reconcile alpha against the
information ratio, label in-sample windows, and are structurally incapable of fabricating a
statistic. A 7B model would produce a worse version of that output, add ~5 GB of resident
memory and a new dependency, and require its own test suite merely to reach parity with
something that currently cannot fail.

Ad-hoc questions that have no tile — *"how did the book do through March 2020?"* — are better
served by SQL in DBeaver against the `analytics` marts. The author can verify their own query;
verifying a model's requires reading the SQL it wrote, at which point the work is already done.
A question asked repeatedly is a signal to add a mart or a tile, which makes it tested and
repeatable rather than reconstructed each time.

## Consequences

- No natural-language interface. The dashboard answers fixed questions; ad-hoc analysis
  happens in DBeaver. New explanations are written as deterministic verdict functions —
  **not** delegated to a model.
- A latent inconsistency is accepted: reporting rules (minimum sample sizes, phase labelling,
  alpha/IR reconciliation) live in the React layer, so `GET /track-record` still returns
  `sharpe: -35.25` for a 2-day window where the UI shows `—`. Defensible with a single
  consumer. **Fix it before adding a second one** by moving those rules into a
  `quantpulse.reporting` module that the API applies before serving.
- If this is ever revisited, the order is fixed: push the reporting rules down first; expose
  tools mapping to endpoints, never a SQL tool; withhold unreliable values from the payload
  rather than annotating them, so the model cannot state what it never received; and gate it
  behind a numeric-grounding test (every number in an answer must appear in a tool result)
  plus a refusal suite for advice-seeking prompts.
- Same reasoning as declining Spark in [roadmap.md](../roadmap.md): the stronger engineering
  signal is evaluating a technology against the problem and being able to say why it was not
  adopted.
