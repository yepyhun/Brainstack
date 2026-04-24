# Phase 55 Context

## why this phase exists

Phases 50 through 54 corrected the main architectural drift:
- Brainstack should be a kernel/mirror, not a behavior governor
- native explicit truth should remain host-owned
- Discord surface truth must not be outranked by transport metadata

That correction was necessary.
It was not sufficient to close the product.

The remaining failure is now narrower and more painful:
- the user can explicitly teach a rule pack
- the bot still may not recall it fully
- the bot still may not behave according to it in ordinary Discord turns
- the Discord surface may still leak lifecycle or warning text

This is why the product still feels broken even after real architecture cleanup.

## what this phase is not

This phase is not:
- another benchmark phase
- another broad UAT-only phase
- another “make the model more obedient” phase
- another Brainstack-governor phase
- another schema or parser design exercise

The problem is no longer “we need more memory cleverness.”
The problem is that explicit user-taught rule-pack truth is still too weakly captured, too weakly recalled, or too weakly delivered on the real Discord surface.

## current observed failure family

The recent Discord traces show the following remaining defect family:

1. explicit rule-pack teaching does not become stable, first-class durable truth reliably enough
2. recall can drift in count or content
3. ordinary turns can still ignore stored explicit truth
4. Discord can still surface internal warnings, lifecycle text, or reset/status noise

These failures are product failures.
They are not theoretical or benchmark-only defects.

## root-cause framing

The most likely remaining root causes are now inside one narrow family:
- explicit pack capture fidelity
- durable pack representation
- pack recall fidelity
- ordinary-turn consumption of stored explicit truth
- Discord delivery boundary cleanliness

The current rule-pack example is only the proof case.
The implementation must solve the general explicit-pack fidelity problem, not special-case the current user.

## non-routes

The following directions are explicitly wrong here:
- more transcript-mined style slots
- more regex extraction for emoji, dash, language, or tone
- new behavior_policy or output_contract expansion
- prompt-only hacks that only fix the current proof case
- warning-driven UX where the bot keeps asking for the rules again
- “partial success” where recall works but ordinary replies still drift

## completion meaning

This phase is only worth closing if the final result is true on Discord itself:
- teach a rule pack
- get full recall
- get compliant ordinary replies
- reset
- get the same truth again
- see no internal leak

Anything less leaves the user-facing product still broken.

