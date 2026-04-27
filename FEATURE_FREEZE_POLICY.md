# Feature Freeze Policy

GA hardening is not feature expansion.

## Allowed

- P0/P1 correctness fix.
- Capability preservation fix.
- Approval, security, privacy, or leak fix.
- Source/wizard/Docker parity fix.
- Observability, failure bundle, doctor, recovery, install, migration, backup/restore work.
- Test/probe automation required to prove supported GA scope.

## Blocked

- New donor lift.
- New memory feature not needed for P0/P1 closure.
- New prompt personality.
- New provider feature.
- Broad refactor without release-blocker evidence.
- Benchmark-specific workaround.
- Live-case phrase blacklist.

## Enforcement

Any proposed work during GA hardening must classify as:

```text
P0/P1 closure
GA proof infrastructure
security/recovery
blocked feature expansion
```

Blocked feature expansion goes to backlog, not current GA hardening.
