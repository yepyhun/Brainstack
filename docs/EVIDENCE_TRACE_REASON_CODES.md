# Evidence Trace Reason Codes

Reason codes are stable public diagnostics for Brainstack memory-kernel decisions.

Rules:
- no free-text drop reasons in committed traces;
- reason codes must come from `brainstack.core.reason_codes.ReasonCode`;
- reason codes explain memory evidence decisions, not Hermes runtime execution;
- adding a reason code requires a test update.

Core codes used by public memory fixtures:

- `selected_authority_match`
- `selected_receipt_backed_fact`
- `selected_cited_corpus`
- `dropped_assistant_claim_not_truth_authority`
- `dropped_corrected_false`
- `dropped_inspect_only`
- `dropped_support_only_for_answer_truth`
- `dropped_scope_mismatch`
- `dropped_budget_overflow`
- `demoted_low_authority`
- `deferred_external_runtime_owner`
- `no_candidate_for_resolved_memory_target`
- `trace_incomplete`
- `raw_private_text_excluded`
- `full_ack_requires_complete_receipt_coverage`

Anti-goal:
- do not create scenario-specific reason codes such as user names, repo names, Discord channel names, or one-off live canary labels.
