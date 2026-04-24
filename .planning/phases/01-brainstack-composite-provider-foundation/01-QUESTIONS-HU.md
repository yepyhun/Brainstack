# Finomhangoló Kérdések

Ezeket a kérdéseket kell lezárni, mielőtt a `brainstack` implementációját érdemben elindítjuk.

## Már rögzített döntések

### 1. Mi a legfontosabb cél?
Elfogadott válasz:

- az `agent okosodása / continuity`, a `token spórolás`, és a `graph / temporal truth` gyakorlatilag holtversenyes első helyen vannak
- a `nagy corpus kezelés` nagyon közeli második, nem halasztható távoli extra

### 2. Mi legyen a built-in Hermes memóriával?
Elfogadott válasz:

- teljes kiszorítás kell
- a built-in memory és a built-in user profile is legyen kikapcsolva
- az új rendszer csináljon mindent ezen a területen

### 3. A személyes dolgok külön polcon legyenek, vagy a nagy tudásrendszer részei?
Elfogadott válasz:

- külön polc kell a személyes identitásnak, preferenciáknak és a közös munkafolytonosságnak

### 4. Az első verzió már tudjon teljes könyvtár-szintű second-braint, vagy induljon szűkebben?
Elfogadott válasz:

- nagy indulás kell

### 5. A rendszer alapból próbáljon minél kevesebb toolt használni, vagy legyen először inkább biztosabb?
Elfogadott válasz:

- alapból max spórolásra legyen hangolva

### 6. Az első verzióba mennyi jövőbeli bővítési helyet építsünk?
Elfogadott válasz:

- előre bővíthető legyen
- ne csak hely maradjon a bővítéseknek, hanem a fontos korai integrációk ténylegesen legyenek is benne

### 7. A My-Brain-Is-Full-Crew és az RTK mennyire legyen része az első körnek?
Elfogadott válasz:

- az RTK legyen már az elején aktív token-spóroló sidecar
- a My-Brain-Is-Full-Crew első körben skill-ekből épülő workflow shell legyen
- ne legyen első napon teljes felső orkhesztrátor
- később csak akkor kaphat erősebb orkhesztrációs szerepet, ha a composite memory stack már stabil

Miért:

- így update-barát marad a rendszer
- nem rakunk rögtön két erős felső orkhesztrátort egymásra
- a workflow és skill előnyöket korán megkapod, de kisebb a szétcsúszás kockázata

## Állapot

Az összes első körös döntés le van zárva. Ez a fájl most már döntésnapló, nem nyitott kérdéssor.
