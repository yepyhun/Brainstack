# Phase 9 Context

## Name
Hindsight Lossless Transcript Hardening

## Objective
Strengthen Brainstack continuity with a Brainstack-internal transcript shelf that keeps raw turn history and bounded session snapshots without introducing a second context engine.

## Depends On
- Phase 2
- Phase 6
- Phase 8

## Key Outputs
1. append-only raw turn shelf inside Brainstack
2. bounded session snapshot / compression hint path
3. evidence-first bounded transcript recall with explicit provenance

## Main Risks
- transcript storage turns into a second continuity path with blurred ownership
- transcript recall becomes noisy default prompt spam
- donor ideas from `hermes-lcm` get copied too literally and hurt update safety
