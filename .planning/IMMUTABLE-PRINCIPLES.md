# Immutable Project Principles

This file is the canonical source for Brainstack's top-level principles.

Do not paraphrase, soften, expand, or reinterpret these principles in other GSD artifacts without an explicit user decision.

If `STATE.md`, `ROADMAP.md`, or a phase plan needs to reference project principles, it should point here instead of drifting into a rewritten variant.

## Scope

These principles are split by purpose:

- Memory-kernel architecture principles define what Brainstack is and is not.
- Development and validation guardrails define how Brainstack work is allowed to proceed.
- Product quality targets define what the system must ultimately deliver in real use.
- GSD planning enforcement defines how every future phase must prove alignment with this file.

## Memory-Kernel Architecture Principles

- Donor-first / upstream respect: Nem kontárkodunk bele a donor architektúrába. Szigorúan tiszteletben tartjuk az upstream, eredeti kódot. Nincsenek gyors lokális hackek, amelyek később megakadályozzák a frissítést vagy elvágják a donorhoz való visszacsatolást.

- Modularity / upstream updateability: A modularitás megőrzése kritikus. Az upstream forrásból való frissíthetőséget soha nem áldozhatjuk fel egy-egy új capability beépítésének kedvéért. Ha egy capability csak úgy építhető be, hogy szétveri a modulhatárokat vagy tartósan fork-szerű állapotot hoz létre, akkor az a megközelítés hibás.

- Synergistic with Hermes / memory kernel is not governor: A Brainstack célja, hogy szinergikusan támogassa Hermest mint memory kernel, nem az, hogy mindent átírjon Hermesben vagy minden runtime problémát memóriaréteggel oldjon meg. A Brainstack tárolhat, visszakereshet és projektálhat kanonikus állapotot, policyt, folytonosságot és evidenciát, de nem válhat scheduler, executor, approval-governor vagy rejtett irányító aggyá. A végrehajtási és governance döntések explicit runtime boundary-khez tartoznak, nem a memória-recallhoz.

- No benchmaxing / no live-case distortion: Hétköznapi, live production használatra fejlesztünk, nem benchmark-pontszámokra. A szintetikus tesztek, például LongMemEval, visszajelzések, nem öncélú végcélok. Ugyanez igaz az éles használatból előkerülő hibákra is: nem az adott éles hibához torzítjuk Brainstacket, hanem univerzálisan működőképesebb memory kernelt építünk. Ha egy változtatás csak egy konkrét problémát old meg, de általánosan nem memory-kernel előrelépés vagy máshol akadályoz, akkor azt a funkciót vagy átalakítást szigorúan tilos megcsinálni.

- Zero heuristic sprawl: Nem építünk kulcsszófarmokra, nyelvspecifikus barkácslogikára vagy rejtett heurisztikus kerülőutakra. Heurisztika legfeljebb szűk boundary guardra vagy input grammar hygiene-re elfogadható, és ott is csak akkor, ha nincs jobb, strukturáltabb megoldás. Heurisztika nem lehet a rendszer fő intelligenciája.

- Multilingual and multimodal by design: Brainstack nem lehet angol-only vagy text-only zsákutca. A tervezésnek természetesen támogatnia kell, hogy kínai, német, magyar vagy más nyelvű felhasználó is használhassa, és hogy a rendszer később képre, dokumentumra, hangra és más modalitykre bővíthető maradjon. Nyelv- vagy modality-specifikus kivétel csak expliciten indokolt boundary adapterben elfogadható.

## Development And Validation Guardrails

- Truth-first / no "good enough": Nem hazudjuk magunknak, hogy valami kész, ha nem az. Minden alrendszert őszintén kell minősíteni: "helyes", "függőben konkrét hiánnyal", vagy "rossz és azonnal javítandó". A zöld állapot nem jelenthet rejtett degraded módot vagy elhallgatott hiányt.

- Fail-closed upstream compatibility: Nincs "félig működő" vagy megtévesztő állapot. Ha egy függőség, backend, adat, config vagy donor seam hiányzik, a rendszernek egyértelműen jeleznie kell a hibát vagy degradációt. Csendes fallback csak akkor megengedett, ha a degraded állapot explicit, inspektálható és nem hazudik capability meglétéről.

- No bandaid/reactive patching: Nem raktapaszolunk rossz eszköz- vagy architektúraválasztást reaktív workaroundokkal. Ha az alapmegközelítés rossz, újra kell tervezni a jobb best-practice megoldás felé. A gyors lokális workaround csak ideiglenes diagnosztikai lépés lehet, nem elfogadott végállapot.

- Inspectability before confidence: Minden érdemi memory-kernel útvonalnak vizsgálhatónak kell lennie. Egy phase nem tekinthető erősnek, ha nem látszik, mi íródott be, mi keresődött vissza, mi esett ki, miért esett ki, és melyik evidence alapján épült a final packet.

## Product Quality Targets

- Coherent continuous conversation: A rendszernek összefüggő, folyamatos, folyékony beszélgetést kell fenntartania.

- Proactive stateful continuity: A rendszernek proaktív, állapottartó folytonosságot kell adnia. Az agent emlékezzen a releváns állapotokra, pending workre és feladatokra, és ezekre megfelelően tudjon reagálni.

- Long-range accurate recall and relation-tracking: A hosszú távú visszakeresésnek és a tények közötti relációk követésének pontosnak kell lennie. A rangsor pontossága elsődleges termékminőségi cél.

- Usable storage of large bodies of knowledge: Brainstacknek képesnek kell lennie nagy tudáskészletek stabil, kereshető és gyakorlatban használható tárolására, nem csak rövid profil- vagy transcript-emlékek kezelésére.

- Meaningful token savings: A rendszernek érdemi token-megtakarítást kell hoznia. Nem olvashat be feleslegesen mindent; szelektív recallt és packet-összeállítást kell használnia.

- Quality priority order: Pontosság > token efficiency > sebesség. A sebesség is fontos: live helyzetben az interaktív útvonal nem válhat elfogadhatatlanul lassúvá, például nem várhatunk 10 másodperces memory-recall késleltetést. Ha hosszabb munka kell, annak explicit async/background vagy inspectable pipeline útvonalon kell futnia.

## GSD Planning Enforcement

Every future GSD phase that touches Brainstack architecture, memory behavior, retrieval, ingestion, host integration, planning, or validation must explicitly check this file.

Each phase context or plan must state:

- which memory-kernel architecture principles it touches;
- why the change is a universal Brainstack improvement, not a benchmark trick or one-case live patch;
- how it preserves donor-first modularity and upstream updateability;
- why it does not turn Brainstack into a governor, scheduler, executor, or hidden host replacement;
- how it avoids heuristic sprawl and language-specific hacks;
- how success will be inspected or measured against the product quality targets.

If a proposed phase cannot satisfy these checks, it must be rewritten, deferred, or rejected before implementation.
