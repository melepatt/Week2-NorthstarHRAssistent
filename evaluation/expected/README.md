# Evaluation Data Contract

Northstar Labs maintains two fixed policy-assistant evaluation partitions:

- `development_questions.json` contains five questions used only for retrieval-score review and
  refusal-threshold calibration.
- `questions.json` contains the locked 15-question final evaluation set. It must not be used to
  select or tune the refusal threshold.

Each answerable record lists atomic policy facts and material qualifications. These points are
scoring criteria, not prewritten target answers. Unanswerable records intentionally contain no
expected facts or document IDs. Question IDs, wording, expected points, and partition membership
should be versioned together so evaluation results remain comparable across releases.
