# Phase 57 Scheduler Truth Proof

## Native scheduler state on installed runtime

Current installed runtime state:

- native cron store exists at:
  - `/home/lauratom/Asztal/ai/finafina/hermes-config/bestie/cron/jobs.json`
- current live job set includes the previously created reminder:
  - `Brainstack logok ellenőrzése`
  - `once at 2026-04-23 14:00`
  - `deliver = origin`
  - `state = scheduled`

This confirms the system does have a real native scheduler. The Phase 57 bug was not “no scheduler exists”; it was false or half-true scheduling semantics.

## Core scheduler fix

Past one-shot schedules are now rejected by scheduler-core.

Direct proof on installed target:

- `create_job(prompt='teszt', schedule='2026-04-22T18:51:00+02:00', ...)`
- result:
  - `ValueError: Requested one-shot schedule is already in the past.`

Valid future one-shot schedules still succeed:

- `create_job(prompt='teszt', schedule='2026-04-22T23:59:00+02:00', ...)`
- result:
  - `state = scheduled`
  - `next_run_at = 2026-04-22T23:59:00+02:00`

This closes the half-wired case where the scheduler previously created a `scheduled` row with `next_run_at = null`.

## Host truth guidance fix

Installed prompt guidance now explicitly states:

- a memory entry is not a scheduled reminder
- a todo note or generic internal task list is not a scheduled reminder
- OS cron/systemd inspection is not valid proof of Hermes scheduler state
- if the native scheduler call fails or is unavailable, the assistant must say so plainly

## Live host-path sanity

Provider-backed temp-home sanity after the stronger guidance:

- when native scheduler tooling was unavailable in that non-gateway host path, the assistant stopped claiming a fake internal reminder queue
- instead it reported that scheduling was unavailable / failed

That is materially better than the earlier fake-success behavior.

## Live Discord delivery proof

A real live Discord delivery proof was captured on the installed runtime.

- proof jobs created against the live Discord thread:
  - `phase57-200935`
  - `phase57m2-201335`
  - `phase57m3-live-proof`
- each produced a real cron output file under:
  - `/home/lauratom/Asztal/ai/finafina/hermes-config/bestie/cron/output/`
- each was later confirmed present in the real Discord thread by reading channel history through the live bot token
- the latest proof job (`b54fbdb6e389`) also proved the new fail-closed lifecycle:
  - output file created
  - job removed from `jobs.json`
  - no retained `delivery_error`

This closes the scheduler truth gap for Phase 57:

- success now corresponds to a real native scheduled job and real Discord delivery
- failed delivery would now remain observable as an error state instead of disappearing as fake success
