# Phase 50 Brainstack Keep / Move / Remove

## execution baseline

- source copy: `/home/lauratom/Asztal/ai/atado/Brainstack-phase50`
- branch: `main`
- head at batch start: `a4ca41651ce815cab770b0d2d338fb7343da2731`

## keep

These remain aligned with the intended product:

### core provider shell
- `brainstack/__init__.py` as the provider entry point
- donor registry access
- provider lifecycle:
  - `initialize`
  - `prefetch`
  - `sync_turn`
  - `shutdown`

### memory orchestration
- `brainstack/retrieval.py`
- `brainstack/task_memory.py`
- `brainstack/operating_truth.py`
- `brainstack/style_contract.py`
- `brainstack/profile_contract.py`
- `brainstack/reconciler.py`
- donor adapters and ingestion pipeline

### authority / ownership / consistency
- principal scope handling
- style authority bootstrap and repair
- task / operating explicit write boundaries
- graph / corpus / continuity coordination

These are memory-kernel concerns, not the problem.

## move

These are not inherently wrong, but they are in the wrong architectural place or too strong on the ordinary chat path:

### behavior policy reinforcement
- current location:
  - `brainstack/behavior_policy.py`
  - `brainstack/control_plane.py`
- target reading:
  - keep as provider-side contract/projection support
  - do not let it become a host-level ordinary-chat governor

### output validation
- current location:
  - `brainstack/output_contract.py`
  - `brainstack.__init__.BrainstackMemoryProvider.validate_assistant_output`
- target reading:
  - keep as provider-owned validation/reporting
  - do not require host ordinary-chat delivery to depend on it as a hard gate

## remove or sharply reduce

These are the parts most likely to have pushed the product into rule-engine shape:

### hard block semantics for ordinary chat
- `validate_output_against_contract(...)` currently returns:
  - `blocked`
  - `can_ship = False`
  - `enforcement = block`
- this is too strong once the host uses it as a critical path

### broad behavior-policy projection pressure
- `build_behavior_policy_reinforcement(...)`
- `behavior_policy_reinforcement` injection through control-plane policy
- this may be acceptable as bounded provider context, but not as the central ordinary-turn steering mechanism

### tests that lock in stronger governance than the product should need
- `tests/test_brainstack_phase42_1_output_enforcement.py`
- parts of `tests/test_brainstack_phase48_live_chat_stabilization.py`
- some older `phase29/30/37` compliance tests

These are valuable as history, but they should not dictate a host-level rule engine if that conflicts with the product target.

## conservative first de-escalation move

The most conservative first move is:

### narrower activation + reduced projection

Not:
- fully deleting output validation
- fully gutting provider-side contract support

Instead:
1. keep provider-side validation/reporting available
2. reduce its projection pressure on ordinary-turn packet assembly
3. narrow the circumstances where it presents itself as blocking/authoritative for ordinary chat
4. let the host stop treating provider validation as a mandatory reply gate

Why this first:
- it preserves donor/provider intelligence
- it avoids a blind “rip out” move
- it directly targets the architectural inversion that broke chat quality

## first code batch implication

The first real de-escalation batch in `Brainstack-phase50` should focus on:

1. auditing `brainstack/output_contract.py`
- determine which violations are truly provider-local repair candidates
- determine which “block” outcomes should become advisory on the ordinary chat path

2. auditing `brainstack/behavior_policy.py` + `brainstack/control_plane.py`
- reduce projection and reinforcement pressure for ordinary chat
- keep explicit style-authority recall intact

3. keeping provider-side traces
- retain `behavior_policy_trace()` and related debug surfaces
- they remain useful for operator proof even after de-escalation

## decision

For the next execute batch:
- keep donor/provider intelligence
- keep memory authority and retrieval
- reduce ordinary-turn behavior projection pressure
- avoid turning Brainstack validation into the main runtime reply gate
