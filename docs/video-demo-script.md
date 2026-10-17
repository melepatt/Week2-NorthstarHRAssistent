# Stakeholder Walkthrough Guide

Target duration: 4 minutes 45 seconds.

## 0:00–0:35 — Purpose and approval status

Open the application title screen. Explain that the assistant answers from six controlled Northstar
Labs HR policy PDFs and refuses unsupported questions. State clearly that the corpus is draft,
People Operations and Legal approval is pending, and the application is not approved for production
or employee reliance.

## 0:35–1:15 — Architecture and policy build

Show `data/source/manifest.json`, one Markdown policy, and its generated PDF. Explain the flow:
deterministic publishing, page-aware extraction, section-aware chunks, Nebius embeddings, persistent
Chroma, startup BM25, reciprocal-rank fusion, reranking, confidence gating, generation, and citation
validation. Note that a clean rebuild produces the same six PDF hashes.

## 1:15–2:05 — Supported single-document question

Ask: “How many paid time off days do full-time employees receive?”

Point out the concise answer and the exact `Leave and Time Off Policy` page citation. Expand “Evidence
and timing” to show the retrieved section, rerank score, and stage timings. Emphasize that displayed
chat history is not sent back with later questions.

## 2:05–2:55 — Supported cross-document question

Ask: “How long is paid parental leave, who is eligible, and what happens to active benefits?”

Confirm that the answer retains the service requirement, duration, continued employee contributions,
and citations from both the leave and benefits documents. Explain that cross-document evidence is
fused by rank and reranked before the top four excerpts reach generation.

## 2:55–3:25 — Refusal behavior

Ask: “What is the current balance in my retirement account?”

Show the standard refusal and referral to People Operations. Note that the chat model is not called
when evidence is absent or below threshold, and invalid citations also become a refusal.

## 3:25–4:15 — Evaluation evidence

Open `docs/evaluation-report.md`. Describe the isolated five-question development set, the locked
15-question final set, and the six quality measures. Show that JSON and CSV retain per-question
evidence, scores, citations, timings, faithfulness decisions, manual-review status, and failure
categories. If the provider-backed run is pending, say so directly; do not substitute unit-test
results for measured quality.

## 4:15–4:45 — Controls and next actions

Close with the release gates: approve policy language, run the opt-in Nebius smoke check, calibrate on
development data, run the fixed final evaluation, manually verify claims against cited pages, address
missed targets, and obtain People Operations and Legal approval before production deployment.
