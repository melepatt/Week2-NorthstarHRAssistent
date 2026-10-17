# Stakeholder Walkthrough Guide

Target duration: 4 minutes 55 seconds.

## 0:00–0:30 — Purpose and approval status

Open the application title screen. Explain that the assistant answers from six controlled Northstar
Labs HR policy PDFs and refuses unsupported questions. State clearly that the corpus is draft,
People Operations and Legal approval is pending, and the application is not approved for production
or employee reliance.

## 0:30–1:15 — Architecture and policy build

Show `data/source/manifest.json`, one Markdown policy, and its generated PDF. Explain the flow:
deterministic publishing, page-aware extraction, section-aware chunks, Nebius embeddings, persistent
Chroma, startup BM25, reciprocal-rank fusion, reranking, confidence gating, generation, and citation
validation. Note that a clean rebuild produces the same six PDF hashes.

## 1:15–1:35 — Development workflow

Show `docs/prompt-log.md`. Explain that Codex supported requirements decomposition, architecture and
test review, implementation assistance, failure analysis, and documentation drafting. Emphasize
that the developer retained the decisions and verified them with offline tests, static checks,
provider-backed model validation, fixed-set evaluation, and manual or visual review. Briefly point
to the recorded prompt, reranker, and confidence-threshold iterations.

## 1:35–2:15 — Supported single-document question

Ask: “How many paid time off days do full-time employees receive?”

Point out the concise answer and the exact `Leave and Time Off Policy` page citation. Expand “Evidence
and timing” to show the retrieved section, rerank score, and stage timings. Emphasize that displayed
chat history is not sent back with later questions.

## 2:15–2:55 — Supported cross-document question

Ask: “How long is paid parental leave, who is eligible, and what happens to active benefits?”

Confirm that the answer retains the service requirement, duration, continued employee contributions,
and citations from both the leave and benefits documents. Explain that cross-document evidence is
fused by rank and reranked before the top four excerpts reach generation.

## 2:55–3:20 — Refusal behavior

Ask: “What is the current balance in my retirement account?”

Show the standard refusal and referral to People Operations. Note that the chat model is not called
when evidence is absent or below threshold, and invalid citations also become a refusal.

## 3:20–4:25 — Evaluation evidence

Open `docs/evaluation-report.md`. Describe the isolated five-question development set, the locked
15-question final set, and its mix of six direct, three cross-document, three ambiguous, and three
unanswerable questions. Show the six quality measures and explain that 100 percent retrieval recall
coexisted with four answerable questions being refused by the confidence gate. Point out the
`8933.0 ms` p95 latency miss and the pending manual review for this exact run. Show that JSON and CSV
retain per-question evidence, scores, citations, timings, faithfulness decisions, manual-review
status, and failure categories.

## 4:25–4:55 — Controls and next actions

Close with the release gates: verify development-set health, review the confidence threshold,
repeat the fixed final evaluation, manually verify claims against cited pages, address the latency
miss, approve policy language, and obtain People Operations and Legal approval before production
deployment.
