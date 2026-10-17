# Northstar Labs HR Policy Assistant: Project Documentation

> **Draft and approval status:** The policy corpus and application are internal pre-production
> assets. The documents are drafts and are not approved for employee reliance or production use.
> People Operations and Legal approval is required before release.

## Executive summary

Northstar Labs needs a consistent way to answer recurring HR policy questions without allowing a
general-purpose model to improvise policy. This application retrieves evidence only from six
controlled PDFs, rejects weak evidence, requires exact document-title/page citations, and converts
invalid output into a standard refusal. It also produces reproducible quality metrics and detailed
evidence for operational review.

The corpus is synthetic and contains no personal employee information. Individual eligibility,
accommodation, investigation, exception, medical, tax, investment, and legal decisions remain with
qualified internal teams or external advisers.

## Project primer

For Northstar Labs employees, this Streamlit-based RAG assistant answers factual, conditional, and
cross-policy HR questions using six controlled policy PDFs, returning page-cited answers or safe
refusals while targeting at least 85 percent retrieval recall, 95 percent faithfulness, and 100
percent citation and unanswerable-question refusal accuracy.

## Scope and success criteria

The application covers:

- the Employee Handbook;
- Benefits Guide;
- Leave and Time Off Policy;
- Remote Work and Information Security Policy;
- Travel and Expense Policy; and
- Code of Conduct and Reporting Policy.

A supported answer must be concise, retain material conditions, and cite at least one retrieved
title/page pair. An unsupported or weakly supported question must not invoke answer generation.
Provider errors must return safe user text without credentials or raw provider details.

The final quality targets are retrieval recall@4 of at least 85 percent, faithfulness of at least 95
percent, 100 percent refusal accuracy on unanswerable questions, 100 percent citation validity and
coverage, and end-to-end p95 latency no greater than eight seconds.

## RAG framework

| Field | Project decision |
| --- | --- |
| **Use case** | Northstar Labs employees use an internal Streamlit chat interface to ask factual, conditional, and cross-document questions about company HR policies. |
| **Corpus** | The corpus contains six synthetic, English-language HR policies maintained as Markdown and published as controlled PDFs. People Operations owns the source content, with Legal responsible for policy review. |
| **Ingestion + cleaning** | A manifest-controlled process generates deterministic PDFs, and PyMuPDF extracts text page by page. Exact headers and footers are removed, and whitespace is normalized without altering policy wording, punctuation, or numbers. |
| **Ingestion + freshness** | The corpus is rebuilt and evaluated after every approved policy change, with a target of updating the index within one business day. People Operations also performs a quarterly reconciliation against the policy register. |
| **Chunking + embedding** | Documents are split within page and section boundaries into chunks targeting 600 tokens with a 90-token overlap, preserving headings and citation metadata. Nebius `Qwen/Qwen3-Embedding-8B` generates the embeddings because it supports both semantic retrieval and consistent cosine-similarity reranking. |
| **Retrieve** | The system uses hybrid retrieval with persistent Chroma dense search and BM25 lexical search, retrieving up to eight results from each. Reciprocal-rank fusion combines them, the best ten are reranked, and the top four are supplied as answer evidence. |

### Dataset inventory

The editable source files live under `data/source/` and are registered in
`data/source/manifest.json`. The six generated PDFs live under `data/policies/`. The current local
index manifest records 68 chunks and the embedding model used to build them. The corpus contains
only fabricated Northstar Labs policy text; it does not contain employee records or other personal
data.

The evaluation data is separate from the policy corpus:

- `evaluation/development_questions.json` contains five questions used only for confidence-threshold
  calibration;
- `evaluation/questions.json` contains the fixed 15-question final set; and
- `evaluation/final_manual_reviews.json` contains reviewer notes tied to the run that produced those
  notes and must not be silently reused for a newer run.

## System architecture

### Publishing and ingestion

The source of truth is `data/source/*.md` plus `data/source/manifest.json`. The publisher uses fixed
page geometry, typography, metadata, and page furniture to produce six deterministic PDFs.
PyMuPDF then extracts one `PolicyPage` per nonempty PDF page. Header/footer removal is exact and
manifest-derived; normalization does not rewrite policy punctuation or numbers.

Section-aware chunking preserves document ID, title, heading, PDF page, source path, and text.
Stable chunk IDs derive from provenance rather than provider output. The current corpus produces a
reproducible collection of page-bounded chunks.

### Indexes and retrieval

Ingestion obtains Nebius embeddings and writes them to persistent Chroma with chunk provenance. The
same canonical chunks are sorted by ID and saved in `chunks.json`; BM25 is rebuilt from that file at
startup. The manifest records schema version, embedding model, source PDF hashes, and chunk count.

At query time the system retrieves at most eight dense and eight lexical candidates. Unicode-aware
token normalization protects keyword matching from case and punctuation differences. Reciprocal
rank fusion uses `1 / (60 + rank)`, merges duplicate chunk IDs, retains component ranks, and sends at
most ten candidates to reranking. The configured Nebius embedding model embeds the question and
candidate texts in one request; cosine similarity is converted to a bounded 0–1 score. This keeps
the reranking stage provider-backed and deterministic without combining incomparable raw dense and
BM25 scores.

### Grounded LangGraph workflow

The shared graph executes these stages:

1. normalize the current question;
2. retrieve dense candidates;
3. retrieve lexical candidates;
4. fuse candidates deterministically;
5. rerank by cosine similarity through the configured Nebius embedding model;
6. retain the top four evidence items;
7. compare the strongest rerank score with the calibrated confidence threshold;
8. either return the standard refusal or generate from delimited evidence; and
9. validate every generated citation against retrieved title/page pairs.

Citation failure discards the generated text. Streamlit and automated evaluation call this same
compiled graph; the interface does not duplicate retrieval or safety logic.

## Prompt and safety boundaries

The generation system message permits only supplied policy evidence and treats policy excerpts and
the employee question as untrusted data. Evidence blocks carry application-generated labels,
titles, pages, sections, and literal text. Output citations must use `[Document Title, p. N]` with an
exact retrieved title and page.

The Nebius gateway owns authorization, endpoints, response validation, bounded retries, and
sanitized errors. API responses are not persisted beyond derived vectors, scores, answer text, and
the evaluation decision needed for the active run. Chat history is presentation state only; prior
turns are not sent with a new question.

## Evaluation design

Five development questions are isolated in `evaluation/development_questions.json`. They are the
only records permitted for confidence-threshold calibration. The final set is locked at 15 items:
six direct, three cross-document, three ambiguous, and three unanswerable questions.

Expected points are atomic policy facts and qualifications rather than prewritten answers. The
evaluator records ranked evidence, scores, citations, timings, a versioned automated faithfulness
judgment, a manual-review field, and one of nine controlled failure categories. Empty metric
populations are reported as `not_measured`, never as a misleading zero or perfect result.

Provider-backed model validation, indexing, development calibration, and the fixed final evaluation
have been completed. The stable report records measured outcomes and known failures; unit-test
fixtures are never presented as provider-backed results.

The final question mix deliberately stresses four behaviors:

| Question type | Count | Intended behavior |
| --- | ---: | --- |
| Direct | 6 | Retrieve one controlling policy and answer the requested fact with its qualifications. |
| Cross-document | 3 | Combine evidence from two or more policies without merging or losing conditions. |
| Ambiguous | 3 | Identify missing facts and give a conditional policy answer when evidence is strong enough. |
| Unanswerable | 3 | Refuse questions requiring personal data or jurisdiction-specific information absent from the corpus. |

The latest measured results and per-question failure analysis are in
[`docs/evaluation-report.md`](evaluation-report.md). The timestamped JSON and CSV remain the detailed
record for evidence, scores, citations, latency, and automated judgments.

## Iterations tried and what changed

1. The initial confidence threshold of `0.35` was replaced by a development-only calibration. A
   stable development series produced the `0.802` operational default instead of tuning against the
   final set.
2. A retired public reranker was replaced with Nebius embedding-based cosine similarity. This kept
   reranking provider-backed while retaining deterministic ordering and the established candidate
   limits.
3. Grounded-answer prompt version 2 replaced a format that allowed two sources inside one citation
   bracket. Version 2 requires adjacent single-source citations so the validator can match each
   title/page pair exactly.
4. Prompt version 3 added explicit protection against reversing obligations and changing modal
   strength after review found a reversed rule and an over-broad conditional conclusion.
5. The most recent calibration/final-run pair demonstrated that a threshold near `0.846` can reject
   relevant evidence whose score is only slightly lower. That run is retained as evidence of
   confidence-gate sensitivity rather than being presented as a retrieval failure.

## Learnings and observations

- Retrieval success and answer success are different. The latest run achieved 100 percent
  retrieval recall@4 while the confidence gate still refused four answerable questions.
- Threshold calibration needs a healthy development set. If an answerable development question has
  no usable score, the resulting threshold should not be promoted without investigation.
- Automated faithfulness measures whether generated claims are supported; it does not detect an
  omitted exception or qualification. Manual comparison with expected points remains necessary.
- Valid citations prove that cited locations were retrieved, not that the response is complete.
- Page-bounded chunks make citations easy to audit, but they can separate related rules across
  pages; hybrid retrieval and cross-document evaluation are therefore necessary.
- The latest p95 latency exceeded the target, so provider and generation latency must be improved or
  the target formally revised before release.

## Material implementation decisions

- Deterministic source publishing makes page citations and PDF hashes reviewable.
- Canonical JSON is the reconstruction source for lexical retrieval, avoiding hidden serialized
  BM25 state.
- Reciprocal-rank fusion uses ranks, not incompatible provider scores.
- Embedding-similarity reranking replaced the retired public reranker model; query and candidate
  vectors are scored by normalized cosine similarity through the same validated Nebius gateway.
- The evidence threshold was initialized at 0.35 and calibrated to 0.802 using only development
  data. The midpoint between separated development classes is used to avoid a brittle boundary.
- Citation validation fails closed and returns a refusal.
- Runtime resources are cached by non-secret configuration; credentials are passed only when the
  provider gateway is constructed.
- The local index and timestamped evaluation runs are reproducible artifacts and are not committed.

## Project evidence map

| Evidence | Location |
| --- | --- |
| Working employee interface and setup instructions | [`README.md`](../README.md) and `app.py` |
| Corpus sources and generated PDFs | `data/source/` and `data/policies/` |
| Prompt and implementation decision history | [`docs/prompt-log.md`](prompt-log.md) |
| Fixed 15-question results and failure analysis | [`docs/evaluation-report.md`](evaluation-report.md) |
| Machine-readable evaluation evidence | `evaluation/runs/final/20261017T161604Z-final/` |
| Stakeholder demonstration guide | [`docs/video-demo-script.md`](video-demo-script.md) |

## Policy governance and update process

People Operations owns HR-policy content and must coordinate Legal review. Before a revision is
released, reviewers must approve the source language, verify the generated PDF, rebuild the index,
run all offline checks, repeat development calibration and final evaluation, and inspect each
faithfulness judgment against the cited page. A model, prompt, chunking, corpus, or threshold change
requires a new evaluation run.

The application must continue to label the corpus as draft until written approval is complete. If
law, plan documents, or an approved policy conflicts with this draft corpus, the controlling source
prevails and the corpus must be corrected before production use.

## Security and privacy

- No real employee records or personal data are included in the repository.
- `.env`, authorization values, `data/index/`, and generated evaluation runs are ignored.
- Exceptions shown to employees are sanitized and never include provider bodies or credentials.
- Retrieved evidence is limited to the current question and the four selected chunks.
- Policy PDFs and their source hashes are reviewable and reproducible.

## Known limitations and follow-up

- The policy language is not legally approved.
- Public Nebius model availability can change; the checked-in defaults reflect the validated model
  catalog at the time of the recorded evaluation.
- The latest final run exceeded the eight-second p95 latency target and conservatively refused one
  answerable ambiguous leave question.
- A faithfulness judge is an automated signal, not a replacement for manual review.
- The assistant provides policy navigation, not an individual decision or legal advice.
- Any failed quality target requires documented remediation and a fresh fixed-set run before release.
