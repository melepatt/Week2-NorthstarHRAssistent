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
