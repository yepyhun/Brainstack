# Phase 64 Context

## current reading

Phase `63` moved ordinary Brainstack hot-path understanding onto local typed substrates. That solved a kernel authority problem, but it did not create bounded proactive execution by itself.

The current gap is runtime-side:

- Brainstack can now carry better state and policy
- Hermes still needs a clean intake and execution contract
- without that contract, the system drifts into narrative claims like “I am already doing it” without tool-grounded proof

## what the user is actually asking for

The desired feel is:

- learns and improves
- proactive rather than reactive
- meaningful token savings
- behaves like an active entity
- still checks with the user on genuinely new or unfamiliar domains

This is not a request for fake autonomy. It is a request for bounded, engineering-grade initiative.

For this phase, that means:

- session-start or wake-time initiative
- explicit pending-work intake
- approval-bounded execution
- no claims of hidden continuous work that the runtime is not actually performing

## what is already available

### Brainstack side

- `live_system_state`
- `operating_context`
- typed task/operating substrates
- local typed understanding
- durable policy memory

### runtime side

- cron wake mechanism
- approval infrastructure in gateway/runtime
- tool execution surface
- session lifecycle hooks

## what is missing

- an explicit inbox-task contract
- a deterministic session-start intake routine
- a metadata-driven approval gate
- typed writeback of execution outcomes

## ownership model to preserve

### Brainstack

- stores and projects authoritative memory/state/policy
- does not become the hidden scheduler or execution engine

### Hermes runtime

- decides what to do at wake or session start
- runs tools
- enforces approval gates
- emits execution writeback through a Brainstack-owned typed seam

## why this is general, not a one-off

This architecture would help any Hermes-based agent that needs:

- restart recovery
- bounded proactivity
- task continuation across sessions
- fewer fake “working on it” claims
- clearer auditability between memory and execution

The local folder names or example scripts are replaceable. The pattern itself is general.

## rejected interpretations

- “make Brainstack itself proactive”
- “make cron the real intelligence”
- “have the runtime guess unknown domains from text”
- “pretend we have a single infinite agent session”

## execution note

This phase is intentionally runtime-heavy. It complements Brainstack but does not reopen the Brainstack ownership boundary set earlier.

The acceptable writeback shape is runtime -> explicit typed seam/provider -> Brainstack durable state.

Execution should proceed in this order:

1. inbox JSON contract freeze
2. bounded startup intake order
3. approval gate
4. typed writeback

The roadmap phase stays singular unless implementation evidence proves it must split.
