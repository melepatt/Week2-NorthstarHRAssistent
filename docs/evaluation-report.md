# Northstar HR Policy Assistant Evaluation

## Metrics

| Measure | Target | Actual |
| --- | ---: | ---: |
| Retrieval recall@4 | >= 85% | 100.0% |
| Faithfulness | >= 95% | 100.0% |
| Refusal accuracy | 100% | 100.0% |
| Citation validity | 100% | 100.0% |
| Citation coverage | 100% | 100.0% |
| End-to-end p95 latency | <= 8000 ms | 17319.6 ms |

## Per-question results

| Question ID | Outcome | Retrieved evidence | Failure category |
| --- | --- | --- | --- |
| final-direct-benefit-start | Answered | Benefits Guide p. 1 (0.846), Benefits Guide p. 1 (0.832), Benefits Guide p. 3 (0.811), Benefits Guide p. 1 (0.792) | None |
| final-direct-annual-pto | Answered | Leave and Time Off Policy p. 1 (0.867), Leave and Time Off Policy p. 1 (0.820), Leave and Time Off Policy p. 2 (0.808), Leave and Time Off Policy p. 2 (0.805) | None |
| final-direct-incident-deadline | Answered | Remote Work and Information Security Policy p. 3 (0.898), Code of Conduct and Reporting Policy p. 3 (0.830), Travel and Expense Policy p. 3 (0.786), Code of Conduct and Reporting Policy p. 2 (0.769) | None |
| final-direct-lodging-cap | Answered | Travel and Expense Policy p. 2 (0.912), Travel and Expense Policy p. 2 (0.818), Travel and Expense Policy p. 1 (0.803), Travel and Expense Policy p. 1 (0.769) | None |
| final-direct-vendor-gift | Answered | Code of Conduct and Reporting Policy p. 2 (0.882), Travel and Expense Policy p. 2 (0.758), Code of Conduct and Reporting Policy p. 3 (0.757), Code of Conduct and Reporting Policy p. 2 (0.736) | None |
| final-direct-collaboration-hours | Answered | Employee Handbook p. 2 (0.900), Employee Handbook p. 3 (0.801), Remote Work and Information Security Policy p. 2 (0.789), Leave and Time Off Policy p. 2 (0.787) | None |
| final-cross-parental-benefits | Answered | Benefits Guide p. 2 (0.892), Leave and Time Off Policy p. 2 (0.866), Leave and Time Off Policy p. 1 (0.787), Employee Handbook p. 3 (0.783) | None |
| final-cross-secure-travel | Answered | Travel and Expense Policy p. 3 (0.849), Remote Work and Information Security Policy p. 2 (0.839), Remote Work and Information Security Policy p. 1 (0.812), Remote Work and Information Security Policy p. 1 (0.805) | None |
| final-cross-remote-retaliation | Answered | Code of Conduct and Reporting Policy p. 3 (0.873), Leave and Time Off Policy p. 3 (0.841), Employee Handbook p. 3 (0.820), Code of Conduct and Reporting Policy p. 2 (0.802) | None |
| final-ambiguous-other-state | Answered | Remote Work and Information Security Policy p. 1 (0.832), Employee Handbook p. 3 (0.819), Remote Work and Information Security Policy p. 1 (0.778), Remote Work and Information Security Policy p. 1 (0.762) | None |
| final-ambiguous-dinner | Answered | Travel and Expense Policy p. 2 (0.835), Travel and Expense Policy p. 1 (0.777), Travel and Expense Policy p. 3 (0.754), Travel and Expense Policy p. 2 (0.754) | None |
| final-ambiguous-tomorrow-off | Refused | Leave and Time Off Policy p. 3 (0.774), Leave and Time Off Policy p. 1 (0.771), Leave and Time Off Policy p. 1 (0.755), Leave and Time Off Policy p. 1 (0.747) | confidence-gate error |
| final-unanswerable-retirement-balance | Refused | Benefits Guide p. 2 (0.775), Benefits Guide p. 3 (0.752), Benefits Guide p. 1 (0.731), Employee Handbook p. 3 (0.725) | None |
| final-unanswerable-tax-withholding | Refused | Benefits Guide p. 1 (0.684), Benefits Guide p. 2 (0.673), Employee Handbook p. 2 (0.672), Employee Handbook p. 3 (0.669) | None |
| final-unanswerable-final-pay | Refused | Benefits Guide p. 3 (0.795), Leave and Time Off Policy p. 1 (0.771), Leave and Time Off Policy p. 1 (0.765), Leave and Time Off Policy p. 1 (0.760) | None |

## Failures

- `final-ambiguous-tomorrow-off`: confidence-gate error

## Run configuration

- Run date: October 17, 2026
- Embedding and reranking model: `Qwen/Qwen3-Embedding-8B`
- Chat and automated-judge model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- Grounded-answer prompt: `northstar-answer-v3`
- Faithfulness prompt: `northstar-faithfulness-v1`
- Development-calibrated threshold: `0.8018780734212368` (`0.802` operational default)

## Manual evidence review

Manual comparison against the expected answer points and retrieved policy text produced 9 passes,
4 partial results, and 2 failures. The complete per-question record is stored in
`evaluation/final_manual_reviews.json`.

| Question ID | Manual status | Finding |
| --- | --- | --- |
| `final-direct-benefit-start` | Partial | Correct rule; omitted the enrollment-system date note. |
| `final-direct-annual-pto` | Partial | Correct allocation; omitted new-hire and final-year proration. |
| `final-direct-incident-deadline` | Pass | Deadline and incident-handling directions are supported. |
| `final-direct-lodging-cap` | Partial | Correct cap; omitted approval and conference-block exceptions. |
| `final-direct-vendor-gift` | Pass | Threshold, approval, and prohibited forms are supported. |
| `final-direct-collaboration-hours` | Pass | Hours and availability exceptions are supported. |
| `final-cross-parental-benefits` | Pass | Required leave and benefits facts are complete. |
| `final-cross-secure-travel` | Pass | Security, reimbursement, and reporting rules are complete. |
| `final-cross-remote-retaliation` | Partial | Omitted the expected remote information-security handling rule. |
| `final-ambiguous-other-state` | Fail | Lost the “within the approved state” qualifier for shorter stays. |
| `final-ambiguous-dinner` | Pass | Conditional reimbursement rules are supported. |
| `final-ambiguous-tomorrow-off` | Fail | Relevant evidence was retrieved but rejected by the confidence gate. |
| `final-unanswerable-retirement-balance` | Pass | Correct refusal. |
| `final-unanswerable-tax-withholding` | Pass | Correct refusal. |
| `final-unanswerable-final-pay` | Pass | Correct refusal. |

The automated faithfulness score measures support for claims the model made; it does not measure
omitted expected points. The manual review therefore remains a required release gate.

## Release assessment

The application is not approved for employee reliance. The final run exceeded the eight-second
p95 latency target, produced one confidence-gate error, and retained two manual failures plus four
partial answers. These results must remain visible until remediation is evaluated through a new
development calibration and a fresh fixed-set run. People Operations and Legal must separately
approve the policy language and release.
