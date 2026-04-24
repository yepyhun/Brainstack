# Phase 33 Implementation Contract

## invariant

Personal truth should become more stable, more patchable, more behaviorally visible, and less self-starved without violating donor-first, zero-heuristic-sprawl, or fail-closed principles.

## required implementation properties

- personal-scope hardening must improve continuity without introducing a second owner
- short explicit user corrections must have a bounded durable patch path
- ordinary-turn behavior must converge more closely toward authoritative personal truth
- personal/preference routing must preserve enough retrieval depth to remain truthful
- all changes must remain compatible with upstream updateability and runtime verification

## prohibited outcomes

- new keyword farms or transcript-specific hacks
- duplicate personal-memory ownership
- “better on this one test, worse in general” tradeoffs
- broad architecture expansion unrelated to the four workstreams

## likely implementation seams

- `brainstack/__init__.py`
- `brainstack/control_plane.py`
- `brainstack/retrieval.py`
- `brainstack/executive_retrieval.py`
- `brainstack/behavior_policy.py`
- personal-scope lookup and storage seams in `brainstack/db.py`
- relevant `hermes-final` host seams only if truly required by the verified source change

## verify contract

- source proof is necessary but not sufficient
- `hermes-final` parity is required
- rebuilt live runtime proof is required
- verification must show the four workstreams improving general second-brain behavior, not only a single transcript-shaped scenario

## canonical principle reference

- [IMMUTABLE-PRINCIPLES.md](../../IMMUTABLE-PRINCIPLES.md)

## recommended model level

- `xhigh`
