# Phase 6 Context

## Name
Native Memory Displacement Completion

## Objective
Finish the cut-over from native Hermes memory behavior to the Brainstack path.

## Depends On
- Phase 1
- Phase 5

## Key Outputs
1. built-in memory off path
2. built-in user profile off path
3. minimal Hermes compatibility patch set

## Main Risks
- hidden native paths remain active
- user profile handling leaks through the old path
- a large host fork is created unnecessarily
