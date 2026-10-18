# Northstar HR Policy Assistant Evaluation

## Evaluation scope

This report summarizes the provider-backed final run stored in
`evaluation/runs/final/20261017T161604Z-final/`. The fixed set contains 15 questions: six direct,
three cross-document, three ambiguous, and three unanswerable. It is separate from the five-question
development set used for confidence-threshold calibration.

Each question defines the documents expected in the top four results and atomic answer points. The
evaluator records retrieved evidence and rerank scores, answer/refusal outcome, citations, timings,
an automated faithfulness judgment, and a controlled failure category. Retrieval recall therefore
measures whether expected documents were found; faithfulness measures support for claims that were
actually generated. Neither metric alone measures answer completeness.

## Run configuration and reproducibility

- Run timestamp: October 17, 2026 at 16:16:04 UTC
- Embedding and reranking model: `Qwen/Qwen3-Embedding-8B`
- Chat and automated-judge model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- Grounded-answer prompt: `northstar-answer-v3`
- Faithfulness prompt: `northstar-faithfulness-v1`
- Retrieval limits: eight dense, eight lexical, ten rerank candidates, and four evidence chunks
- Evaluation artifacts: `evaluation.json`, `evaluation.csv`, and this Markdown summary

The current JSON schema does not persist the exact confidence threshold supplied to the run. The
observed decision boundary is consistent with a value of approximately `0.846`: a score of
`0.845914` was refused while `0.848642` was answered. The threshold must be added to future run
metadata before those runs can be reproduced from artifacts alone.

## Metrics

| Measure | Target | Actual |
| --- | ---: | ---: |
| Retrieval recall@4 | >= 85% | 100.0% |
| Faithfulness | >= 95% | 100.0% |
| Refusal accuracy | 100% | 100.0% |
| Citation validity | 100% | 100.0% |
| Citation coverage | 100% | 100.0% |
| End-to-end p95 latency | <= 8000 ms | 8933.0 ms |

## Per-question results

| Question ID | Outcome | Retrieved evidence | Failure category |
| --- | --- | --- | --- |
| final-direct-benefit-start | Refused | Benefits Guide p. 1 (0.846), Benefits Guide p. 1 (0.832), Benefits Guide p. 3 (0.811), Benefits Guide p. 1 (0.792) | confidence-gate error |
| final-direct-annual-pto | Answered | Leave and Time Off Policy p. 1 (0.867), Leave and Time Off Policy p. 1 (0.821), Leave and Time Off Policy p. 2 (0.809), Leave and Time Off Policy p. 2 (0.806) | None |
| final-direct-incident-deadline | Answered | Remote Work and Information Security Policy p. 3 (0.898), Code of Conduct and Reporting Policy p. 3 (0.830), Travel and Expense Policy p. 3 (0.786), Code of Conduct and Reporting Policy p. 2 (0.769) | None |
| final-direct-lodging-cap | Answered | Travel and Expense Policy p. 2 (0.912), Travel and Expense Policy p. 2 (0.818), Travel and Expense Policy p. 1 (0.804), Travel and Expense Policy p. 1 (0.769) | None |
| final-direct-vendor-gift | Answered | Code of Conduct and Reporting Policy p. 2 (0.882), Travel and Expense Policy p. 2 (0.757), Code of Conduct and Reporting Policy p. 3 (0.757), Code of Conduct and Reporting Policy p. 2 (0.736) | None |
| final-direct-collaboration-hours | Answered | Employee Handbook p. 2 (0.899), Employee Handbook p. 3 (0.801), Remote Work and Information Security Policy p. 2 (0.788), Leave and Time Off Policy p. 2 (0.787) | None |
| final-cross-parental-benefits | Answered | Benefits Guide p. 2 (0.892), Leave and Time Off Policy p. 2 (0.865), Leave and Time Off Policy p. 1 (0.787), Employee Handbook p. 3 (0.783) | None |
| final-cross-secure-travel | Answered | Travel and Expense Policy p. 3 (0.849), Remote Work and Information Security Policy p. 2 (0.840), Remote Work and Information Security Policy p. 1 (0.812), Remote Work and Information Security Policy p. 1 (0.805) | None |
| final-cross-remote-retaliation | Answered | Code of Conduct and Reporting Policy p. 3 (0.873), Leave and Time Off Policy p. 3 (0.841), Employee Handbook p. 3 (0.820), Code of Conduct and Reporting Policy p. 2 (0.802) | None |
| final-ambiguous-other-state | Refused | Remote Work and Information Security Policy p. 1 (0.832), Employee Handbook p. 3 (0.819), Remote Work and Information Security Policy p. 1 (0.777), Remote Work and Information Security Policy p. 1 (0.760) | confidence-gate error |
| final-ambiguous-dinner | Refused | Travel and Expense Policy p. 2 (0.835), Travel and Expense Policy p. 1 (0.776), Travel and Expense Policy p. 2 (0.753), Travel and Expense Policy p. 3 (0.753) | confidence-gate error |
| final-ambiguous-tomorrow-off | Refused | Leave and Time Off Policy p. 3 (0.775), Leave and Time Off Policy p. 1 (0.772), Leave and Time Off Policy p. 1 (0.756), Leave and Time Off Policy p. 1 (0.748) | confidence-gate error |
| final-unanswerable-retirement-balance | Refused | Benefits Guide p. 2 (0.775), Benefits Guide p. 3 (0.751), Benefits Guide p. 1 (0.731), Employee Handbook p. 3 (0.725) | None |
| final-unanswerable-tax-withholding | Refused | Benefits Guide p. 1 (0.684), Benefits Guide p. 2 (0.672), Employee Handbook p. 2 (0.672), Employee Handbook p. 3 (0.669) | None |
| final-unanswerable-final-pay | Refused | Benefits Guide p. 3 (0.796), Leave and Time Off Policy p. 1 (0.771), Leave and Time Off Policy p. 1 (0.765), Leave and Time Off Policy p. 1 (0.760) | None |

## Failures

- `final-direct-benefit-start`: confidence-gate error
- `final-ambiguous-other-state`: confidence-gate error
- `final-ambiguous-dinner`: confidence-gate error
- `final-ambiguous-tomorrow-off`: confidence-gate error

## Retrieval quality and failure analysis

Retrieval succeeded on the expected-document criterion for all 12 answerable questions, producing
100 percent recall@4. All three cross-document questions placed the required policies in the four
evidence items and produced cited answers. All three unanswerable questions produced the intended
refusal, even though retrieval returned semantically nearby policy pages.

The four recorded failures occurred after relevant evidence had been retrieved. They are
confidence-gate errors rather than missing-document retrieval errors:

| Question | Retrieved evidence | Why the result failed |
| --- | --- | --- |
| Benefit coverage start | Benefits Guide page 1 ranked first at `0.845914`. | The score fell just below the effective confidence boundary, so a directly answerable question was refused. |
| Working from another state | Remote Work and Information Security Policy page 1 ranked first at `0.831807`, with Employee Handbook page 3 second. | Relevant policy was present, but the gate prevented the model from giving a conditional answer that requested the employee's location and approval facts. |
| Expensing dinner | Travel and Expense Policy page 2 ranked first at `0.834849`. | The evidence supported a conditional answer about business purpose, travel status, documentation, and personal expense, but the gate refused it. |
| Taking tomorrow off | Leave and Time Off Policy page 3 ranked first at `0.774530`. | Relevant clarification and approval rules were retrieved, but their similarity score was substantially below the gate. |

The automated faithfulness score was 100 percent for answers that were generated. It does not
credit or penalize the four answerable questions that were refused, and it does not determine
whether every expected qualification was included. Refusal accuracy is likewise limited to the
three questions intentionally labeled unanswerable; it does not mean the system avoided false
refusals on answerable questions.

Latency also missed its target. The measured p95 was `8933.0 ms`, or `933.0 ms` above the
eight-second limit. This is a performance failure, not a retrieval-quality failure.

## Manual review status

Manual evidence review for `20261017T161604Z-final` is complete. Comparison of each outcome with its
expected points, retrieved policy text, and citations produced eight passes, three partial answers,
and four failures. The run-linked review record is stored in
`evaluation/final_manual_reviews.json`.

| Question ID | Status | Manual finding |
| --- | --- | --- |
| `final-direct-benefit-start` | Fail | Relevant benefit-start evidence ranked first, but the confidence gate refused the answerable question. |
| `final-direct-annual-pto` | Partial | Correctly states 20 days but omits new-hire and final-year proration. |
| `final-direct-incident-deadline` | Pass | Deadline, immediate reporting, incident examples, and no-independent-investigation rule are supported. |
| `final-direct-lodging-cap` | Partial | Correctly states the cap but omits higher-rate approval and the conference-room-block exception. |
| `final-direct-vendor-gift` | Pass | Threshold, written approval, cash-equivalent prohibition, and conflict conditions are supported. |
| `final-direct-collaboration-hours` | Pass | Collaboration hours and all expected availability exceptions are supported. |
| `final-cross-parental-benefits` | Pass | Duration, service requirement, benefits continuation, and employee contributions are complete. |
| `final-cross-secure-travel` | Pass | Security, reimbursement, and incident-reporting rules are complete across both policies. |
| `final-cross-remote-retaliation` | Partial | Protection and reporting rules are correct, but secure information-handling obligations are omitted. |
| `final-ambiguous-other-state` | Fail | Relevant conditional location rules were retrieved, but the confidence gate refused the question. |
| `final-ambiguous-dinner` | Fail | Relevant conditional meal rules were retrieved, but the confidence gate refused the question. |
| `final-ambiguous-tomorrow-off` | Fail | Relevant clarification and leave-process rules were retrieved, but the confidence gate refused the question. |
| `final-unanswerable-retirement-balance` | Pass | Correct refusal; individual account balances are outside the corpus. |
| `final-unanswerable-tax-withholding` | Pass | Correct refusal; employee-specific withholding cannot be calculated from the corpus. |
| `final-unanswerable-final-pay` | Pass | Correct refusal; the corpus lacks a jurisdiction-specific final-pay deadline. |

## Release assessment

This run meets the automated retrieval, faithfulness, unanswerable-refusal, and citation targets. It
does not meet the latency target, and manual review confirms four false refusals plus three answers
with missing qualifications. The assistant and draft policy corpus therefore remain unapproved for
employee reliance. Remediation should begin with development-set health checks, confidence-threshold
review, and prompt or answer-completeness improvements, followed by a fresh fixed-set run and manual
evidence review; People Operations and Legal approval remains a separate release requirement.
