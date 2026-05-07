# Enterprise Release Compliance Boundary

Brainstack has local memory-kernel release proof.

That is not the same as strict enterprise procurement readiness.

## Current Rule

- Normal Brainstack release is governed by `scripts/run_memory_kernel_release_checklist.py`.
- Strict enterprise claim is governed by `scripts/verify_enterprise_release_compliance.py`.
- Missing legal/security artifacts must block enterprise wording, not hide memory-kernel proof.

## Reproduce

```bash
python scripts/verify_enterprise_release_compliance.py --out /tmp/brainstack_enterprise_compliance.json
```

## Boundary

The enterprise compliance report is public-safe and local. It does not upload code, logs, DBs, tokens, sessions, or private runtime state.

If the report says `strict_enterprise_claim_allowed: false`, release notes must not claim strict enterprise readiness.
