# phase 29 context

## title

live communication-contract recall and post-reset durability forensics

## problem

New live Bestie evidence contradicts the earlier settled reading that Brainstack-only ownership of the personal-memory / communication-contract axis is holding after reset.

After reset, the deployed runtime can still recall:

- the user's name
- some personal facts
- the Bestie naming convention in parts of the thread

But it fails to reliably recall or apply:

- Humanizer-style communication rules
- the full communication contract
- the prohibition against falling back into skill/local/net detours for this axis

The visible symptoms are not just stylistic drift. The runtime falls back into the wrong operational behavior:

- cheerful default tone
- emoji usage
- wrong restatement of the rules
- skill/local/network lookup detours instead of Brainstack-owned recall

## north star

After reset, the same principal should recover one coherent personal-memory state:

- identity still holds
- communication-contract still holds
- the runtime does not narrate memory internals
- the runtime does not reach for skill/local/net detours to recover personal style truth

The target is not "better than before".
The target is one end-to-end personal-memory path that survives reset without splitting identity from style contract.

## why this matters

This is not a cosmetic issue.

It means the personal-memory axis may currently be split:

- identity can survive
- style / communication contract can drop

If that reading is true, then the project does not currently have a clean end-to-end durable path for communication-contract truth after reset.

## settled constraints

- keep Brainstack-only ownership on the personal-memory axis
- do not reintroduce persona-file, skill-file, or notes-file bandaids
- do not treat prompt hardening as the answer until the storage/retrieval/application seam is proven
- do not collapse this into donor work unless the forensic trace points there

## anti-goals

- do not call this fixed just because the assistant can still recall the user's name
- do not accept a partial success where style rules are missing but the runtime sounds plausible
- do not replace durable recall with ad hoc local search, skill lookup, or network lookup
- do not explain the failure away as "weak prompting" without proving the deeper seam
- do not reopen settled donor/updateability questions unless the live trace forces it

## live evidence to explain

- session reset occurs
- the assistant still knows `Tomi` and some durable personal facts
- the assistant forgets or misapplies the Humanizer rules
- the assistant attempts non-Brainstack recovery behaviors such as skill/local/net lookup

## final forensic findings

- durable Humanizer / formatting / language rows did exist in `profile_items`
- those rows were stored as legacy unscoped `preference:*` rows even though they belonged to a principal-scoped personal-memory lane
- before repair, the live database showed `12` active preference rows and `0` scoped preference rows
- before repair, with the actual live principal scope, the active communication contract recovered only the Bestie naming rule and dropped the broader Humanizer contract
- before repair, with no principal scope applied, the same contract builder surfaced the missing Humanizer / formatting / language rules immediately
- this ruled out a pure application-only story, because the contract was already missing before generation
- the failing `2026-04-16` reset sessions produced no new profile writes
- container logs showed both the Tier-2 worker and the session-end flush failing with `TypeError: call_llm() got an unexpected keyword argument 'response_format'`
- the reset-time promotion crash was a second real seam, not just noise:
  - it blocked new scoped communication-preference writes from landing after restatement
- the repair that closed the main seam was bounded:
  - deterministic open-time backfill for legacy unscoped principal-scoped profile rows when transcript evidence resolves to one unique principal scope
  - Tier-2 caller fix from direct `response_format=` to `extra_body={\"response_format\": ...}`
- after repair, the deployed docker runtime showed:
  - `15` scoped profile keys
  - `12` scoped preference keys
  - `3` scoped identity keys
- after repair, a fresh deployed-path `AIAgent._build_system_prompt()` call on the real docker target recovered:
  - Bestie naming
  - one-thought-per-line formatting
  - `Én / Te / Ő` capitalization
  - Hungarian language requirement
  - the Humanizer-style lines
- after repair, isolated runtime provider proof showed `on_session_end()` can again flush a scoped preference row end-to-end
- transcript metadata for the failing live sessions still uses the older principal shape (`agent_identity:default`, `agent_workspace:hermes`, numeric Discord user id)
- that principal-model drift remains real, but it is adjacent to the confirmed seam and was not required to explain or close the regression

## forensic hypothesis table

| hypothesis | what would be true | how to falsify it |
| :--- | :--- | :--- |
| ingest gap | the Humanizer rules never became durable Brainstack truth in the first place | inspect ingest/write path and stored artifacts for the same session/user |
| retrieval gap | rules are stored durably but not selected at recall time | compare stored communication-contract truth with recalled packet composition |
| contract-assembly gap | recalled rows exist but the active communication contract is built from the wrong subset | trace contract assembly inputs and final packed contract |
| application gap | the contract is present but runtime defaults override it | inspect final prompt/input assembly and live reply behavior |
| stale deployed path | source-of-truth is fixed but the running runtime/home/config path bypasses it | prove runtime parity and trace the reset path on the deployed target |

## required outcome

This phase is complete only when the project can name the real failing seam with evidence.

The correct output of this phase may be either:

- a bounded fix plan tied to one proven seam
- or an explicit falsification of the user's current theory, if the trace proves the failure is elsewhere

## final seam verdict

- primary seam:
  - legacy unscoped principal-scoped communication preferences were being dropped at the scoped retrieval / active-contract boundary
- secondary correctness bug:
  - Tier-2 worker and session-end flush could fail before promotion because the Tier-2 caller used an unsupported `response_format` keyword
- ruled out:
  - total absence of durable communication data
  - pure prompt weakness
  - pure application / override failure after a correct contract was already present
- smallest correct repair surface:
  - Brainstack store compatibility/backfill at open-time
  - Tier-2 caller argument fix
- what was intentionally not changed:
  - no persona-file fallback
  - no skill-file memory path
  - no host prompt hardcode
  - no broad principal-model rewrite inside Phase 29

## final verdict shape

The closeout for this phase should end in one explicit verdict:

- seam:
  - ingest
  - durable shape
  - retrieval
  - contract assembly
  - application / override
  - stale deployed runtime path
- what was ruled out
- smallest correct repair surface
- what must not be changed as part of the repair
