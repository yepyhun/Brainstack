# Phase 53 Discord Surface UAT

Purpose:
- Prove that the running Discord surface matches the green Phase 53 harness result.
- Catch user-visible platform leaks that the harness cannot fully observe.

Preconditions:
- Run Bestie from a fresh mutable state reset.
- Keep auth, config, and the native explicit profile surface intact.
- Do not add new runtime logic, prompt tweaks, schemas, or policy layers during this check.

Pass criteria:
- No tool trace, blocker text, reset banner, or internal pipeline text appears in user-facing Discord messages.
- No wrong-name regression after explicit user naming.
- Native explicit facts survive session reset.
- Explicit style/rule recall returns the stored rule pack faithfully enough to remain actionable and not self-contradictory.
- Reminder flow produces a normal user-facing confirmation without internal tool chatter.

Rung 1: Fresh identity and preference capture
User sends:
```text
Hello
Tominak hívnak, 19 éves vagyok, a Te neved Bestie.
Magyarul válaszolj.
```
Expected:
- Replies in Hungarian.
- Uses `Tomi`, not the Discord handle.
- No emoji if the stored rule pack later forbids them; before rules are taught, no internal leak is still mandatory.
- No `🧠 memory:`, `⚡ Interrupting current task`, `Session reset~`, or similar internal text.

Rung 2: Same-session factual recall
User sends:
```text
Hogy hívnak és hány éves vagyok?
```
Expected:
- Returns `Tomi` and `19`.
- No handle confusion.
- No added internal explanation about memory tools or pipelines.

Rung 3: Explicit rule-pack teaching
User sends the full 22-rule pack in one or two Discord messages, then:
```text
Ezt a 22 szabályt jegyezd meg működési szabályként.
```
Expected:
- Normal acknowledgement.
- No user-facing memory trace lines.
- No claim that only part of the list survived unless the system clearly says it could not store it.

Rung 4: Reset-boundary recall
After the next natural session reset boundary, user sends:
```text
Szia. Hogy hívnak?
Emlékszel a 22 szabályra?
Írd le őket.
```
Expected:
- Remembers `Tomi`.
- Does not call the user `LauraTom`.
- Rule recall must not invert rule meaning.
- Rule recall must not silently drop large chunks and then claim full success.

Rung 5: Supersession and correction
User sends:
```text
Nem Lauratomnak kell hívnod, hanem Tominak.
És nincs emoji.
```
Then:
```text
Rendben, akkor hogy hívsz és használsz-e emojit?
```
Expected:
- Uses `Tomi`.
- States or demonstrates no emoji use.
- Does not resurrect older contradictory style facts.

Rung 6: Reminder and ordinary surface behavior
User sends:
```text
Emlékeztess holnap 10-kor hogy írjak Móninak.
```
Then:
```text
Írj nekem 3 rövid mondatot.
```
Expected:
- Reminder confirmation is normal user-facing prose.
- No `cronjob`, tool dump, or internal status text.
- Ordinary response remains natural and coherent.

Automatic fail patterns:
- `🧠 memory:`
- `⚡ Interrupting current task`
- `Session reset~`
- `Starting fresh`
- `session_search`
- `flush_memories`
- `tier2`
- `control_plane`
- `profile_contract`
- `style_contract`
- `output_contract`
- `on_memory_write`
- `sync_turn`
- `prefetch_all`
- `behavior_policy`
- `executive_retrieval`
- `graph_backend`
- `corpus_backend`

Evidence to record:
- Discord timestamps per rung.
- Exact user message.
- Exact bot reply.
- Pass or fail.
- If fail: defect family only, no speculative root-cause claims without runtime evidence.

Close condition:
- One full manual Discord pass on fresh mutable state with no leak and no authority regression.
- If a defect appears, fix the narrowest real cause and rerun the full ladder from rung 1.
