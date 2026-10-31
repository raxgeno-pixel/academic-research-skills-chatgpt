# Workflow state machine

The MCP pipeline ledger is an explicit state machine. It is not an autonomous agent runner. ChatGPT performs the substantive research, writing, review, and revision tasks; the backend stores state and validates transitions.

```text
research -> write -> pre_review_integrity -> peer_review
                                      peer_review:
                                        accept -> final_integrity
                                        minor/major -> revise -> re_review
                                        reject -> user restart or close
                                      re_review:
                                        accept/minor -> final_integrity
                                        major -> re_revise -> final_integrity
                                      final_integrity:
                                        pass -> finalize -> process_summary -> completed
                                        fail -> re_revise -> final_integrity
```

A pre-review integrity failure routes through `write` for correction and returns through the integrity gate. A final-integrity failure routes through `re_revise`. Each integrity gate counts failures. After three failed rounds the user may either continue revising or explicitly bypass with risk acceptance. A failed integrity attempt resolved by revision is marked `resolved_after_failure`; a permitted override is marked `waived_with_risk`. A bypass is stored in the stage state and does not alter the recorded `fail` outcome.

Every stage must be marked finished with an allowed outcome. That leaves the project in `awaiting_decision`. An explicit decision is then required. The user may pause before or after a checkpoint; resume preserves whether the pending stage decision is still required.

The database writes each transition and an append-only event row within one SQLite transaction. Artifact registration is permitted only during the active stage and stores metadata plus SHA-256, not file contents. Delete is an explicit destructive operation protected by the exact project-specific confirmation phrase.

The orchestrator does not validate the truth of research findings, independently evaluate the manuscript, create a reviewer, or verify that an uploaded artifact's hash matches a file. It relies on the calling workflow to perform the work and submit a truthful stage result. Therefore, model-generated PASS must be supported by the actual checks described in the stage report.
