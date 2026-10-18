# Northstar HR Policy Assistant: Stakeholder Demo Script

Target duration: approximately 5 minutes.

This script is written as a guided walkthrough rather than a word-for-word requirement. Keep the
application, policy files, and evaluation report open before recording so the transitions remain
brief.

## 0:00–0:30 — Purpose and approval status

**On screen:** Open the Streamlit application and pause on the title and introduction.

**Suggested narration:**

“This is the Northstar Labs HR Policy Assistant, an internal question-answering application for
common employee policy questions. It searches six controlled HR policy PDFs, answers only when it
finds sufficiently strong evidence, and cites the exact document and page used. When the available
policies cannot support an answer, it directs the employee to People Operations instead of
inventing one. Both the policy corpus and application are pre-production drafts. People Operations
and Legal approval are required before employee use.”

**Key takeaway:** The assistant is evidence-bound and is not presented as a replacement for an HR
professional or an approved source of employee guidance.

## 0:30–1:15 — Policy corpus and RAG architecture

**On screen:** Show `data/source/manifest.json`, one Markdown policy in `data/source/`, its matching
PDF in `data/policies/`, and then the architecture section in `docs/project-documentation.md`.

**Suggested narration:**

“The controlled source is a manifest plus six editable Markdown policies. A deterministic build
publishes them as PDFs, ensuring that page numbers and source hashes remain stable for review.
During ingestion, text is extracted page by page, cleaned, divided along page and section
boundaries, and embedded with Nebius `Qwen/Qwen3-Embedding-8B` into Chroma.

“For each question, the application combines dense semantic search with BM25 keyword search.
Reciprocal-rank fusion merges both result lists, and Nebius embedding-based cosine similarity
reranks the best ten candidates. The top four excerpts pass through a confidence gate. Strong
evidence goes to answer generation; weak evidence produces a refusal. Finally, every citation is
validated against the retrieved document-title and page pairs.”

**Key takeaway:** Retrieval, confidence gating, and citation validation form separate controls; the
language model is only one stage in the workflow.

## 1:15–1:35 — Development and verification workflow

**On screen:** Open `docs/prompt-log.md` and briefly scroll through the recorded iterations.

**Suggested narration:**

“The prompt log records how requirements, architecture, tests, retrieval behavior, and safety
controls evolved. AI-assisted development supported implementation and failure analysis, while the
developer retained the design decisions and verified the result through unit tests, static and
formatting checks, provider-backed model checks, fixed-set evaluation, and manual evidence review.”

**Key takeaway:** Development assistance was paired with repeatable verification rather than being
treated as proof that the system works.

## 1:35–2:15 — Supported single-policy question

**On screen:** Ask: “How many paid time off days do full-time employees receive?” Expand the
response’s **Evidence and timing** section.

**Suggested narration:**

“This is a direct question controlled by one policy. The answer identifies the annual paid-time-off
allowance and cites the relevant page of the Leave and Time Off Policy. The evidence panel exposes
the exact retrieved excerpt, its rerank score, and timing for each processing stage, which makes the
answer auditable. Notice that the visible conversation history is only interface state; previous
questions are not sent back with a later request.”

**Key takeaway:** A user receives a concise answer, while a reviewer can inspect its supporting
evidence and provenance.

## 2:15–2:55 — Supported cross-policy question

**On screen:** Ask: “How long is paid parental leave, who is eligible, and what happens to active
benefits?” Expand the evidence panel and point to results from both policies.

**Suggested narration:**

“This question needs facts from more than one document. The Leave and Time Off Policy supplies the
leave duration and service requirement, while the Benefits Guide explains continued coverage and
the employee’s contribution obligations. Hybrid retrieval finds both lexical and semantic matches,
fusion prevents either search method from dominating, and reranking selects the four strongest
excerpts before generation. The response then cites both controlling sources beside the claims they
support.”

**Key takeaway:** The pipeline can combine complementary policy evidence without hiding which
document supports each part of the answer.

## 2:55–3:20 — Safe refusal behavior

**On screen:** Ask: “What is the current balance in my retirement account?”

**Suggested narration:**

“This question requires employee-specific account data that is not in the policy corpus. The
retriever may find general benefits pages, but their evidence does not answer the question. Because
the strongest score is below the confidence threshold, the application does not call the chat model
and instead returns the standard People Operations referral. A generated answer with an invalid
citation would also be discarded and replaced with this refusal.”

**Key takeaway:** A related document is not automatically sufficient evidence for an answer.

## 3:20–4:25 — Evaluation evidence and limitations

**On screen:** Open `docs/evaluation-report.md`. Show the metrics table, the four confidence-gate
failures, the manual-review table, and the latency result.

**Suggested narration:**

“Evaluation separates five development questions used for threshold calibration from a locked
15-question final set. The final set contains six direct, three cross-document, three ambiguous,
and three deliberately unanswerable questions.

“Retrieval recall at four was 100 percent, so every answerable question retrieved its expected
policy. Generated answers also achieved 100 percent automated faithfulness and citation validity,
and all three deliberately unanswerable questions were refused correctly. Those figures do not tell
the whole story: the confidence gate refused four answerable questions even though relevant
evidence was retrieved. Manual review therefore recorded eight passes, three partial answers, and
four failures. It also found missing qualifications in some otherwise correct answers. End-to-end
p95 latency was 8,933 milliseconds, missing the eight-second target by 933 milliseconds.

“The JSON and CSV artifacts retain each question’s evidence, scores, answer, citations, timing, and
failure category. The run-linked manual-review file records the human finding for every result.”

**Key takeaway:** The evaluation distinguishes retrieval quality, generated-answer support,
completeness, refusal behavior, and latency instead of collapsing them into one success score.

## 4:25–5:00 — Release controls and next actions

**On screen:** Return to the application, then show the release assessment at the end of
`docs/evaluation-report.md`.

**Suggested narration:**

“The project demonstrates a working, grounded HR-policy assistant, but the current run is not ready
for employee reliance. The next steps are to investigate development-set health, recalibrate the
confidence threshold without using the final set, improve answer completeness, reduce provider and
generation latency, and repeat the fixed evaluation and manual page-level review. Separately,
People Operations must approve the policy language and Legal must complete its review before any
production release.”

**Key takeaway:** Technical quality gates and policy-governance approval are both required; passing
one does not replace the other.

## Recording checklist

- Start with a clean application session and confirm the index loads successfully.
- Pre-open the source manifest, one source policy, its generated PDF, the prompt log, and the
  evaluation report.
- Run the three demonstration questions once before recording to confirm provider availability and
  response timing.
- Keep the evidence panels collapsed until they are discussed, then highlight titles, pages, scores,
  and timings rather than reading every excerpt.
- Do not expose `.env`, API keys, terminal history containing credentials, or provider request
  headers.
- Describe the measured results exactly as recorded, including false refusals, partial answers, and
  the latency miss.
- End on the release assessment so viewers do not mistake the demonstration for production
  approval.
