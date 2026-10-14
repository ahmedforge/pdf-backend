# Answer and citation evaluation

## What this measures

This is a small, reproducible **synthetic smoke benchmark**, not a general RAG
accuracy claim. It exercises real upload, page extraction, chunking, MiniLM
retrieval, Groq generation, and the same structured SSE endpoint used by the UI.
Three original, non-private PDFs contain distinct facts across three pages each.
The corpus contains 18 answerable and 6 deliberately unanswerable questions.
No production user documents or credentials are included.

## Recorded run

- Date: 2026-10-14T15:54:34.292340+00:00.
- Backend source: `402cf2c`; runtime backend code unchanged by this evaluation.
- Environment: isolated local FastAPI/PostgreSQL API; real Groq `openai/gpt-oss-20b`.
- Embeddings: packaged MiniLM; `top_k=5`, default minimum similarity 0.30.
- Completed requests: **24/24**.
- Expected-answer match: **23/24**.
- Answerable fact match: **18/18**.
- Correct abstention heuristic: **5/6**.
- Citation hits on the expected physical page containing the expected fact:
  **18/18** answerable questions.
- Support precision among citation markers on answerable questions:
  **100.0%**.
- Time to first token: p50 **1.042s**,
  p95 **1.781s**.
- Complete response: p50 **1.247s**,
  p95 **1.797s**.

Latency includes local API retrieval plus network/model time. These are one-run,
warm/local measurements, not Azure cold-start, concurrent-load or phone latency.
The model has no fixed sampling seed; repeated runs may differ. p95 uses the
nearest-rank method. Failures stay in the accuracy denominator; latency describes
only successfully completed requests.

## Failure analysis

| Document | Question | Actual answer |
| --- | --- | --- |
| bikes | What brand are the bicycles? | The bicycles are Juniper. [Chunk 0] |

The bicycle brand is absent from the document. The model inferred it from the
fleet name, Juniper, and attached a real citation that does not support that
claim. A valid page link alone is not proof of a correct answer. This failure is
recorded without changing retrieval thresholds or prompts to improve this score.

## Scoring limits and manual review

Answer match searches for expected facts, with word boundaries and normalization
of equivalent digit/number-word forms. It can miss valid paraphrases or accept an
answer containing a correct fact alongside an incorrect claim. Abstention is a
phrase heuristic. Citation support requires a matched chunk marker, expected
page, and expected fact in the source text; it does not establish entailment of
every claim. All 24 answers were also read during this run; the listed unsupported brand inference was confirmed against the fixture. Inspect [all raw answers](../evaluation/results/local/results.json)
before using the numbers. Extend this corpus with longer public PDFs, multi-page
reasoning, tables, contradictions, and OCR cases before claiming broad accuracy.

## Reproduce

Start a local backend with a real PostgreSQL/pgvector database and Groq key.
Do not point this at somebody else's API. Then run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python scripts/evaluate_answers.py \
  --base-url http://localhost:8000 \
  --output evaluation/results/my-run
```

The runner generates selectable-text PDFs, registers a disposable account,
uploads only its own fixtures, streams 24 questions seven seconds apart to
respect the limiter, and deletes only the documents it created in a finally
block. It writes results after every answer. It does not retry or hide failed
questions. The disposable account remains because no account-delete endpoint
exists; account identifiers/passwords/tokens are not saved to results. If the
process is killed before cleanup, remove only that disposable account's fixtures.
Generated PDFs and [summary](../evaluation/results/local/summary.json) are included.
The four scorer/fixture tests run in the full backend suite.
