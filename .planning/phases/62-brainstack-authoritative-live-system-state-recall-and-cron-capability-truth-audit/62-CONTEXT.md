# Phase 62 Context

## why this phase exists

The live system just exposed a deeper problem than "the answer was slow".

The user asked whether previously built autonomous mechanisms still worked. The assistant should have answered from current state. Instead:
- it drifted toward checking cron/files reactively
- a cron test later claimed it had no file-write capability
- the durable Brainstack state was not serving as authoritative live-system truth

This means the memory kernel is still not holding the right kind of truth for "what is currently live".

## current live facts

### 1. the communication contract is still present

The canonical deployed `USER.md` still contains the communication rules and controlled-autonomy contract.

This proves the system did not simply "forget everything".

### 2. the active cron store is empty

The live `jobs.json` currently shows no active jobs.

That matters because ordinary user questions about heartbeat / pulse / evolver cannot be answered truthfully by replaying earlier transcript claims if the live scheduler state is empty.

### 3. Brainstack stores old autonomous-system claims mostly in the wrong lanes

The live Brainstack DB contains heartbeat / evolver / pulse-related material in:
- `continuity_events`
- `transcript_entries`
- `profile_items`

Examples include:
- old heartbeat deployment claims
- old "dynamic pulse" statements
- evolver path / project-focus profile fragments

But the live query evidence so far does not show authoritative, current-state `operating_records` carrying those mechanisms in a clean, currently-valid form.

### 4. ordinary questions about live mechanisms therefore become unstable

Because authoritative current-state operating truth is weak or absent:
- restart/session boundaries make the system rely on residue
- transcript/continuity claims stay semantically retrievable
- the model can answer as if earlier setup is still current

That is a Brainstack-owned memory-authority failure.

### 5. the cron file-write incident is real, but the current evidence does not support "real permission denial" yet

The cron session artifact:
- `session_cron_d0c8894058fb_20260423_170000.json`

contains only:
- the cron system prompt
- the assistant final response claiming no filesystem-write tools were available

It contains no tool call.

So the current evidence does **not** say:
- the system tried to write and got denied

It currently says:
- the model declared incapability without attempting the operation

### 6. the current cron scheduler surface does not obviously explain that claim

Current scheduler construction shows:
- `disabled_toolsets=["cronjob", "messaging", "clarify", "hermes-discord"]`

This is strong evidence that the no-write-tools answer is not yet proven as a true permissions boundary.

The more likely interpretations are:
- tool-surface visibility mismatch inside cron sessions
- capability-truth failure
- prompt/tool-selection failure

This must be recorded, but it remains a boundary issue unless it directly contaminates Brainstack durable truth.

## validated external-audit findings

An external audit proposed several claims. The current evidence validates them unevenly.

### validated as materially correct

1. cron runs use fresh sessions and do not inherit ordinary memory
   - current scheduler builds session ids like `cron_<jobid>_<timestamp>`
   - current cron agent construction sets:
     - `skip_memory=True`
     - `skip_context_files=True`
   - this is real and explains why cron cannot rely on ordinary session-memory continuity

2. `brainstack_pulse.py` is operationally weak
   - the live script at `/opt/data/home/tools/tomij/brainstack_pulse.py`:
     - reads pending tasks from a markdown file
     - prints status markers
     - appends to `pulse_log.txt`
   - it does **not** directly notify the agent, enqueue authoritative Brainstack state, or trigger a durable handoff path

3. `native_moa_research.py` is not standalone-autonomous in the current runtime
   - the live script imports `hermes_tools`
   - running it directly in the container succeeds only in a degraded sense:
     - it reports `ERROR: hermes_tools nem elérhető`
     - then writes a report file anyway
   - so the audit is directionally correct that it is not cleanly portable outside Hermes-managed execution context

4. Evolver is installed but not running as a background loop
   - the CLI exists under `/opt/data/home/brainstack/evolver`
   - `node index.js --help` works
   - current process listing shows no active evolver loop process

### validated only in weaker form

5. `pip` is absent, but "dependencies are not installable" is too strong
   - host-level `pip` is absent
   - container-level `pip` is absent from the checked paths
   - but `uv` is present
   - therefore the stronger claim is:
     - the current environment is not set up for naive `pip` workflows
     - not that Python dependencies are fundamentally impossible to install

6. "cron jobs did not persist" is too strong as a universal statement
   - current live `jobs.json` does contain the `Brainstack Pulse Test` job
   - current cron output directories also show persisted historical job outputs, including `f0e34b7d8d67`
   - therefore the validated claim is narrower:
     - the cron state and the assistant's claims about it have been inconsistent
     - not that cron persistence categorically never works

## planning consequence

Phase 62 should carry forward only the validated core:
- Brainstack lacks authoritative current-system-state truth
- stale transcript residue can outrank live-state truth
- cron capability-truth can fail independently of actual tool denial

Phase 62 should **not** inherit these unvalidated or overstated forms:
- "cron persistence never works"
- "missing pip alone explains autonomy failure"
- "all autonomous failure is one generic cron bug"

## accepted root-cause model for planning

The primary Brainstack defect is:
- live autonomous-system truth is not stored/projected authoritatively enough

The visible consequences are:
- stale assistant narration survives better than current operating truth
- ordinary questions about heartbeat/evolver/pulse are answered from residue or ad hoc checking behavior

The linked cron incident is a secondary finding:
- cron may have a capability-truth problem
- but current evidence does not support classifying it as a Brainstack root cause

## why this is still a Brainstack phase

This remains a Brainstack phase because the universal defect is:
- the memory kernel does not adequately distinguish
  - currently live system state
  - previously established but now absent system state
  - stale assistant narration about system state

That is Brainstack-owned truth authority, not generic cron maintenance.
