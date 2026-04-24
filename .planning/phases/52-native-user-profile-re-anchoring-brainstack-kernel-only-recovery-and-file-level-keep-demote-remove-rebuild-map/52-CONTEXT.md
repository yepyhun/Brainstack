# Phase 52 Context

## why this phase exists

The current problem is no longer “make Brainstack smarter.”

The current problem is authority placement.

Hermes already has a native explicit profile path:
- built-in memory tool
- built-in review/write loop
- provider mirroring hook
- host-side memory manager seam

Brainstack should fit around that.

Instead, the system drifted into a shape where Brainstack sometimes tried to be:
- explicit profile owner
- style governor
- behavior engine
- memory kernel

Those should not all be the same thing.

This phase exists to separate them again:
- native Hermes owns explicit user profile truth
- Brainstack owns memory-kernel augmentation and consistency

## what the first draft still lacked

The first draft was directionally right but not yet strong enough to guarantee the target product level.

Three gaps made it too weak:
- no explicit authority precedence contract between native profile truth and Brainstack-held truth
- no migration/re-anchor contract for already-existing Brainstack profile/style state
- no anti-regression gate preventing Brainstack from silently growing a shadow explicit profile authority again

The review added four more concrete hardening points:
- anchor to the native explicit-memory seam, not to raw markdown filenames as if the file format were the product contract
- define a one-way idempotent mirror contract so native writes cannot bounce back as new explicit truth
- name the exact style-residue rebuild seams that must be closed
- require installer/doctor/README/host-payload/tests/docs parity in the same phase

Without those, the phase could still end in a cleaner but still ambiguous system.

This updated version closes those planning gaps.

## native host reading

The native host already exposes the right anchors:
- `run_agent.py`
  - enables built-in memory and user profile
  - runs review prompts that can save user preferences
  - bridges built-in writes to the external memory provider
- `tools/memory_tool.py`
  - owns the built-in explicit user vs memory write surface
  - already distinguishes `target == \"user\"` from `target == \"memory\"`
- `agent/memory_manager.py`
  - coordinates the built-in provider plus one external provider
  - already exposes `on_memory_write()` mirroring
- `agent/memory_provider.py`
  - defines the contract external providers are supposed to follow
- `agent/prompt_builder.py`
  - already frames user profile as describing the user, not the live runtime

This is a strong sign that native profile primacy is not a new idea. It is the existing donor shape.

The product contract should therefore anchor to this seam, not merely to the current markdown filenames.

## current mismatch

Brainstack still carries custom profile/governance files that are useful in bounded form, but too strong if treated as first-class profile authority:
- `plugins/memory/brainstack/profile_contract.py`
- `plugins/memory/brainstack/style_contract.py`
- `plugins/memory/brainstack/behavior_policy.py`
- `plugins/memory/brainstack/output_contract.py`
- `plugins/memory/brainstack/control_plane.py`

When these become more important than the native `USER.md` / `MEMORY.md` path, the product drifts:
- user facts become ambiguous
- style rules compete with ordinary chat behavior
- memory support turns into rule governance

The surrounding repo/tooling also still carries brainstack-first assumptions in places such as:
- README guidance
- installer logic
- doctor expectations
- host payload and proof surfaces

If those do not move together with the code, the product lands in another hybrid half-state.

## target reading

Wanted end state:
- native Hermes explicit profile path first
- Brainstack mirror and augmentation second
- one coherent host
- one explicit profile authority
- one donor-first memory kernel

Not wanted:
- parallel profile systems
- ordinary-turn style governance as the center of gravity
- host and provider disagreeing about who owns user truth

## authority reading

The target is not merely that native profile is preferred.

The target is:
- explicit native profile truth has first-class primacy
- Brainstack may mirror and support it
- Brainstack may keep bounded archival style truth
- inferred or extracted Brainstack profile signals stay supporting unless promoted through the native explicit path
- mirrored native truth is one-way and idempotent
- native-unavailable mode is explicit, not reconstructed from residue

That is the difference between one coherent product and two overlapping truth systems that happen to agree most of the time.

## planning consequence

The next execution phase after this should not start by coding blindly.

It should start with this map:
- which files remain host-native authorities
- which Brainstack files remain kernel-owned
- which Brainstack files are demoted to bounded archival or advisory roles
- which bridging seams must be rebuilt around native writes
- how current live state migrates to that model
- how shadow authority re-growth is prevented later
- how installer/doctor/docs/payload/tests stay in parity with that architecture
- what the system says when native explicit authority is unavailable

That is the minimum planning truth needed before another serious recovery batch.
