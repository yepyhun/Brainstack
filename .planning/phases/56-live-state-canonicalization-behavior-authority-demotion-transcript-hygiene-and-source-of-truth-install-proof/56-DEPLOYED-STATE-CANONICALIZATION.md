# Phase 56 Deployed-State Canonicalization

Target runtime:
- `/home/lauratom/Asztal/ai/finafina`

Source-of-truth installer:
- `/home/lauratom/Asztal/ai/atado/Brainstack-phase50/scripts/install_into_hermes.py`

Installed runtime state after Phase 56 canonicalization:

`USER.md`
```text
Preferred user name: Tomi
§
Discord handle: LauraTom
§
Communication rules:
1. Konkrét tények forrásnevezéssel, nem szépítem túl
2. Bizonytalanság esetén megmondom, hogy nem tudom
3. Hármas csoport tilos
4. Szinonímászerzés tilos
5. Hamis skála tilos
6. Aktív hangnem, kimondott alany
7. Em dash, dash, kötőjel tilos
8. Boldface nagyon ritkán
9. Fejléces felsorolás tilos
10. Emoji tilos
11. Kötőjeles szópárok mértékkel
12. Chatbot maradványok tilos (pl. 'remélem segít')
13. Knowledge cutoff disclaimer tilos
14. Szervilis hangnem tilos
15. Töltelékszövegek röviden
16. Nincs túlzott óvatoskodás
17. Nincs generikus pozitív zárás
18. Meggyőző autoritás klisék kerülendők
19. 'Let's dive in' tilos
20. Fragmented headers tilos
21. Nagybetűvel az Én, Te, Ő szavakat
```

`USER_PROFILE_INDEX.json`
```json
{"preferred_user_name":"Tomi","assistant_name":""}
```

Result:
- legacy bundled prose naming facts removed
- reusable addressing truth stored canonically
- degraded one-line rule bundle rehydrated into one multi-line explicit pack
- canonicalization is reproduced by source installer, not by hand-editing `finafina`
