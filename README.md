# Northstar Labs HR Policy Assistant

> **Approval gate:** The included policies are internal drafts. They have not been approved for
> production or employee use. People Operations and Legal must approve every policy and the
> assistant's release before deployment.

The Northstar Labs HR Policy Assistant is an internal retrieval-augmented generation application
for questions about six controlled HR policy PDFs. It combines persistent dense retrieval,
in-memory BM25 search, reciprocal-rank fusion, Nebius embedding-similarity reranking, a confidence
gate, grounded answer generation, and exact title/page citation validation. Unsupported questions
receive a deterministic refusal and are directed to People Operations.

## Repository status

- The complete offline implementation and test suite are available.
- The policy corpus contains synthetic company policy text and no real employee data.
- Live Nebius model validation, indexing, and the fixed provider-backed evaluation have been run.
- The latest final run met the automated retrieval, faithfulness, unanswerable-refusal, and citation
  targets. It retained four confidence-gate false refusals, exceeded the p95 latency target, and
  still requires run-specific manual review; see the evaluation report.
- Draft policy content must not be presented as effective policy.

## Delivery package

| Deliverable | Location |
| --- | --- |
| Working Streamlit bot | `app.py` with the setup and run instructions below |
| Six-document HR policy corpus | `data/source/`, `data/source/manifest.json`, and `data/policies/` |
| Architecture, dataset, ingestion, retrieval, iterations, and learnings | [`docs/project-documentation.md`](docs/project-documentation.md) |
| Prompts, AI-assisted engineering decisions, and iteration history | [`docs/prompt-log.md`](docs/prompt-log.md) |
| Fixed 15-question results, retrieval scores, and failure analysis | [`docs/evaluation-report.md`](docs/evaluation-report.md) |
| Machine-readable final-run evidence | `evaluation/runs/final/20261017T161604Z-final/` |
| Under-five-minute stakeholder walkthrough | [`docs/video-demo-script.md`](docs/video-demo-script.md) |

Before external handoff, record the walkthrough in five minutes or less and provide either a
dedicated repository link or a sanitized source archive. Include the evaluation report with that
handoff, and verify that `.env`, credentials, local indexes, caches, and unreviewed request logs are
excluded. The walkthrough guide is complete, but the recording and dedicated distribution link are
separate delivery artifacts and are not stored in this repository.

## Prerequisites

- Python 3.12
- `uv` for reproducible environment management
- A Nebius Token Factory API key with access to the configured embedding and chat models

## Setup

From this directory:

```bash
uv sync --extra test
source .venv/bin/activate
cp .env.example .env
```

Set `NEBIUS_API_KEY` in `.env` or export it through an approved secret-management mechanism. Never
commit `.env`, credentials, authorization headers, local vector indexes, or evaluation runs that
may contain request details.

The application reads process environment variables. After editing `.env`, load it into the active
shell without printing its contents:

```bash
set -a
source .env
set +a
```

The defaults are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1/` | OpenAI-compatible API base |
| `NEBIUS_EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-8B` | Dense embeddings |
| `NEBIUS_RERANK_MODEL` | `Qwen/Qwen3-Embedding-8B` | Cosine-similarity candidate reranking |
| `NEBIUS_CHAT_MODEL` | `Qwen/Qwen3-30B-A3B-Instruct-2507` | Grounded answer and evaluation judge |
| `RERANK_MIN_SCORE` | `0.802` | Development-calibrated evidence-confidence threshold |

Validate credentials and model availability:

```bash
python scripts/check_models.py
```

## Build and ingest the policy corpus

Generate the six deterministic PDFs from the reviewed Markdown sources:

```bash
python scripts/build_policy_corpus.py
```

Build the local Chroma and BM25-compatible canonical index:

```bash
python scripts/ingest.py
```

Ingestion builds in a temporary sibling directory, verifies the manifest, and then swaps the new
index into `data/index/`. A failed build cannot replace the last complete index.

## Run the employee interface

```bash
streamlit run app.py
```

The interface sends only the current question to the shared LangGraph workflow. Prior chat messages
are displayed locally but are not included in provider requests. Expand “Evidence and timing” to
inspect retrieved policy pages and stage latency for a supported answer.

## Test and quality checks

Run all offline tests:

```bash
python -m pytest -q
```

Run static and formatting checks:

```bash
python -m ruff check .
python -m ruff format --check .
```

The live check is opt-in and incurs provider usage:

```bash
RUN_LIVE_TESTS=1 python -m pytest -m live -q
```

## Calibrate and evaluate

Use only the five development questions to select the confidence threshold:

```bash
python scripts/evaluate.py --dataset development --output-dir evaluation/runs/development
```

Before accepting the reported value, verify that every answerable development question retrieved
usable evidence and that the answerable and unanswerable score distributions are credible. A corpus
gap or empty score on an answerable development item invalidates that calibration for promotion.

Copy a reviewed calibrated value into the final command without changing the fixed 15-question set.
The command below uses the stable `0.802` operational default:

```bash
python scripts/evaluate.py --dataset final --output-dir evaluation/runs/final --threshold 0.802
```

Replace `0.802` only when a healthy development run supports a different value. The evaluator writes
timestamped JSON, CSV, and Markdown artifacts and refreshes `docs/evaluation-report.md`. The current
run format does not serialize the selected threshold, so record it in the reviewed report until that
metadata gap is corrected. After every final run, restore the report's methodology and explanatory
analysis if the generated summary replaced them, then manually verify each answer against its
expected points and cited PDF pages.

## Architecture

```text
Markdown policies -> deterministic PDFs -> page extraction -> section-aware chunks
       -> Nebius embeddings -> persistent Chroma
       -> canonical chunks.json -> startup BM25

question -> dense + lexical retrieval -> RRF -> Nebius cosine reranking -> confidence gate
         -> grounded generation -> exact citation validation -> answer or refusal
```

Both `app.py` and `scripts/evaluate.py` obtain the same compiled graph from
`northstar_rag.runtime.create_runtime`. Provider response shapes remain behind the Nebius gateway;
domain objects carry only the evidence, citations, scores, and timings needed by the application.

## Policy update procedure

1. Obtain People Operations and Legal approval for revised policy language.
2. Update the matching file under `data/source/` and its version in `data/source/manifest.json`.
3. Run `python scripts/build_policy_corpus.py`.
4. Review every generated PDF for content, pagination, headers, and approval status.
5. Run `python -m pytest -q` and the repository hygiene checks.
6. Run `python scripts/ingest.py` to build the local index from the approved PDFs.
7. Re-run development calibration and the fixed final evaluation; complete manual review.
8. Deploy only after People Operations and Legal approve the documents and measured behavior.

## Troubleshooting

- **`NEBIUS_API_KEY is required`:** load the key through the approved environment or secret store.
- **Configured model unavailable:** run `python scripts/check_models.py` and set an available model
  ID explicitly; do not silently substitute models after evaluation.
- **Reranking configuration:** `NEBIUS_RERANK_MODEL` must name an embedding-capable model. The
  gateway embeds the question and fused candidates together, then converts cosine similarity to a
  bounded 0–1 confidence score.
- **Policy index is not ready:** run `python scripts/ingest.py` after building the PDFs.
- **Provider service error:** retry after checking Nebius availability. The client performs at most
  two bounded retries for timeouts, rate limits, and server errors.
- **Answer refused despite relevant policy:** inspect rerank scores and retrieved pages, then use the
  development partition to review the threshold. Never tune against the final partition.

## Additional documentation

- [Project documentation](docs/project-documentation.md)
- [Prompt and decision log](docs/prompt-log.md)
- [Evaluation report](docs/evaluation-report.md)
- [Stakeholder demo guide](docs/video-demo-script.md)
