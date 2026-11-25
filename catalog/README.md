# Disziplin-Katalog

Hier liegen die Disziplinen, die Schiesshub kennt. Der Server liest dieses Verzeichnis bei jedem Start ein. Wer eine Disziplin ergänzen oder korrigieren will, ändert eine YAML-Datei und öffnet einen Pull Request. Code muss dafür niemand anfassen.

## Aufbau

```
catalog/
  <verband>/
    katalog.yaml          Kopf: Verband, Regelwerk, Stand, Hinweise
    klassen.yaml          Wettbewerbsklassen (optional)
    startrecht.yaml       Startrecht der Klassen je Wettbewerb (optional, braucht Klassennummern)
    gruppen/
      <gruppe>.yaml       eine Datei je Disziplingruppe
```

Aktuell enthalten:

- `bds/` mit 191 Disziplinen in 25 Gruppen (Sporthandbuch Teil K und L, Fassung des BVA-Genehmigungsbescheids vom 30.06.2026).
- `dsb/` mit 119 Disziplinen in 46 Gruppen, 77 Klassen und 98 Startrechtszeilen (Sportordnung des DSB, Ausgabe Stand 01.01.2027; Startrecht laut Tabelle zur Deutschen Meisterschaft). Status Entwurf, 28 von 46 Gruppen geprüft.

## Eine Gruppendatei

```yaml
schema: 1
verband: "bds"
gruppe:
  id: "kw-25m-praezision"       # = Dateiname
  name: "KW 25 m Präzision"
  waffenart: "kurzwaffe"        # kurzwaffe | langwaffe | flinte | armbrust | bogen | blasrohr | licht
  distanz_m: 25
  art: "praezision"
wertung:
  modell: "ringe"               # siehe Wertungsmodelle
  rangfolge: "absteigend"       # absteigend = höher ist besser
  geprueft: false               # true erst nach Abgleich mit dem Sporthandbuch
ablaeufe:
  praezision-2x10:              # frei wählbarer Schlüssel, eindeutig in der Datei
    beschreibung: "20 Schuss: 2×10 in je 5 Min."
    varianten:
      - id: "standard"
        name: "Standard"
        abschnitte:
          - id: "praezision"
            name: "Präzision"
            serien: 2
            schuss_je_serie: 10
            zeit_je_serie_s: 300
disziplinen:
  - kennziffer: "1001"          # eindeutig je Verband, immer als Text
    name: "Pistole bis 9 mm"
    waffe: "Pistole"
    munition: "bis 9 mm; MI 125 (9 mm) bzw. 112,5 (.38 WC u. kleiner)"
    visierung: "offen"
    anschlag: "stehend"
    scheibe: "Kurzwaffenscheibe"
    ablauf: "praezision-2x10"   # Verweis auf ablaeufe
    hinweis: "max. 1400 g"
```

Optionale Felder einer Disziplin: `optional: true` (wird nicht mehr auf Deutschen Meisterschaften ausgetragen), `pruefen: ["visierung"]` (Angabe ist unsicher und muss nachgesehen werden), `fruehere_kennziffer: "1310"` (die Disziplin lief früher unter dieser Kennziffer; im Sporthandbuch in Klammern genannt).

Werte für `gruppe.art`: `praezision`, `speed`, `kombi`, `fallscheibe`, `fallscheibe-gk`, `fallscheibe-kk`, `mehrdistanz`, `zeitserie`, `fertigkeit`, `symbolscheibe`, `intervall`, `auflage`, `dreistellung`, `laufende-scheibe`, `vogelbaum`, `wurfscheibe`, `feldbogen`, `bogen-3d`.

### Abschnitte

Ein Ablauf besteht aus Varianten (zum Beispiel Bezirks-, Landes-, Deutsche Meisterschaft), jede Variante aus Abschnitten. Aus den Abschnitten baut das Erfassungsterminal seine Eingabemaske.

| Feld | Bedeutung |
|---|---|
| `serien` | Anzahl Serien |
| `schuss_je_serie` | feste Schusszahl je Serie |
| `max_schuss_je_serie` | Obergrenze, wenn die Schusszahl nicht fest ist (Fallscheibe) |
| `ziele_je_serie` | Anzahl Scheiben oder Fallscheiben je Serie |
| `zeit_je_serie_s` | feste Zeit je Serie in Sekunden |
| `zeiten_s` | Zeit je Serie, wenn sie sich von Serie zu Serie ändert |
| `max_zeit_je_serie_s` | Zeitobergrenze je Serie |
| `zeit_wird_gemessen` | die gemessene Zeit geht in die Wertung ein |
| `zuschlag_je_stehender_scheibe_s` | Zeitzuschlag je nicht gefallener Scheibe |
| `distanzen_m` | Entfernung je Serie bei Mehrdistanz |
| `zeit_je_schuss_s` | Sichtzeit je Schuss beim Intervall |
| `pause_zwischen_schuessen_s` | Zeit, in der die Scheibe zwischen zwei Schüssen weggedreht ist (Intervall) |
| `sollzeit_s` | Sollzeit für den ganzen Abschnitt; darüber gilt `abzug_je_voller_sekunde_ueber_sollzeit` (Mehrdistanz-Parcours) |
| `max_gesamtzeit_s` | Abbruchzeit für den ganzen Abschnitt (Mehrdistanz-Parcours) |
| `positionen` | Anschlag je Serie, ein Eintrag je Serie (siehe unten) |
| `ringwerte` | mögliche Ringwerte je Treffer, absteigend ohne Wiederholung (Speed: `[10, 7, 0]`) |
| `zeit_bei_abbruch_s` | Serienzeit bei Zeitlimit oder Abbruch durch den Schützen (Fallscheibe: 60) |
| `zuschlag_stoerung_vor_erstem_schuss_s` | Zuschlag bei Waffenstörung vor dem ersten Wertungsschuss (Fallscheibe: 50) |
| `trefferaufnahme_nach` | Trefferaufnahme nach diesen Serien, 1-basiert und aufsteigend, z. B. `[2, 4]`; nur zur Information |
| `serien_gewertet` | nur die ersten N Serien zählen. Im Katalog nicht setzen: Das ist eine Turnier-Einstellung, die das Turnier-Modul mit demselben Format prüft. |
| `zeit_plausibel_faktor` | Eingabeschutz, keine Sportregel: Eine gemessene Zeit über Faktor × Zeitlimit (`max_zeit_je_serie_s` bzw. `max_gesamtzeit_s`) gilt als Tippfehler. Zahl ≥ 1; ohne Angabe 3, ohne Zeitlimit gilt eine Stunde. Für Turnier-Abweichungen und eigene Disziplinen. |
| `zeit_plausibel_max_s` | Eingabeschutz: feste Obergrenze für gemessene Zeiten in Sekunden, hat Vorrang vor dem Faktor |
| `wettkampfzeit_s` | Gesamtzeit für alle Wertungsschüsse des Abschnitts. Der DSB nennt meist eine Gesamtzeit statt einer Zeit je Serie. |
| `vorbereitung_probe_s` | Vorbereitungs- und Probezeit vor dem ersten Wertungsschuss |
| `probeschuesse` | Zahl der Probeschüsse oder `"unbegrenzt"` |

Auf Ebene der Variante gibt es `wettkampfzeit_gesamt_s`: eine gemeinsame Zeit für alle Abschnitte, z. B. beim Dreistellungskampf.

Ein Ablauf kann ein `finale` beschreiben, nur zur Information: `{ teilnehmer: 8, hinweis: "…", abschnitt: "SpO 15.1.1" }`. Der Hinweis steht in eigenen Worten, nicht im Wortlaut des Regelwerks.

Bei Mehrdistanz stehen die Varianten für die Parcours-Varianten des Sporthandbuchs, nicht für Meisterschaftsebenen.

### Positionen

`positionen` beschreibt je Serie, aus welcher Position, in welchem Anschlag und auf welche Scheibe geschossen wird. Die Liste hat so viele Einträge wie `serien`. Ist auch `distanzen_m` gesetzt, muss `distanz_m` dazu passen.

```yaml
positionen:
  - nr: 6                       # Positionsnummer laut Sporthandbuch
    distanz_m: 15
    anschlaege:                 # eine oder mehrere erlaubte Alternativen
      - { haltung: "kniend", hand: "beidhaendig" }
      - { haltung: "stehend", hand: "schwache_hand" }
    scheibe: 2                  # optional: n-te Scheibe von links
```

| Feld | Werte |
|---|---|
| `haltung` | `stehend`, `kniend`, `liegend`, `sitzend` |
| `aufgelegt` | `true` beim Auflageschießen |
| `hand` | `beidhaendig`, `einhaendig` (Hand freigestellt), `starke_hand`, `schwache_hand`; bei Langwaffe und Flinte weglassen |

### Wertungsmodelle

| `modell` | Ergebnis |
|---|---|
| `ringe` | Summe der Ringe |
| `ringe_minus_zeit` | Ringe abzüglich Sekunden (Speed) |
| `ringe_mit_zeitabzug` | Ringe, abzüglich eines Rings je voller Sekunde über der Sollzeit (Mehrdistanz) |
| `zeit_plus_zuschlaege` | Summe der Zeiten plus Zuschläge, niedriger ist besser (Fallscheibe) |

Weitere Felder unter `wertung`:

| Feld | Bedeutung |
|---|---|
| `gleichstand` | Kriterien bei Ergebnisgleichheit in ihrer Reihenfolge, z. B. `zehner`, `innenzehner`, `neuner_abwaerts`, `parcours_zeit` (niedrigere Parcourszeit gewinnt), `letzte_serie_rueckwaerts` (letzte 10-Schuss-Serie, dann rückwärts), `stechen`, `zehntel_gesamt`. Fehlt, wenn das Regelwerk keine Regel nennt. Was ein Kriterium bedeutet, steht beim jeweiligen Verband in der Gruppendatei als Kommentar. |
| `zehntelwertung` | `true`: Ringe mit einer Nachkommastelle (0 und 1,0 bis 10,9) |
| `stechen_bis_platz` | Ringgleichheit auf den Plätzen 1 bis N wird durch Stechen entschieden |
| `hoechstergebnis_gleicher_rang` | `true`: Wer das erzielbare Höchstergebnis erreicht, wird ohne Finale nicht unterschieden und teilt sich den Rang (DSB SpO 0.12.1). Nur bei `modell: "ringe"` |
| `stechen_bei_hoechstergebnis` | `true`: Gleichstand beim erzielbaren Höchstergebnis entscheidet ein Stechen, vor der Gleichstandskette (DSB SpO 9.4.3). Nur bei `modell: "ringe"`, nicht zusammen mit `hoechstergebnis_gleicher_rang` |
| `gleichstand_serie` | Woraus `letzte_serie_rueckwaerts` die verglichenen Serien bildet: `"zehn_schuss"` (Blöcke zu 10 Schuss, DSB SpO 0.12.1) oder `"serie"` (Serien wie im Ablauf, z. B. 25er bei Flinte). Ohne Angabe: `"serie"`, wenn alle Abschnitte nur Treffer zählen, sonst `"zehn_schuss"` |
| `gleichstand_bis_platz` | Zahl N: `gleichstand` gilt nur für Gleichstände, die auf Platz 1 bis N beginnen (z. B. DSB SpO 9.4.1: 6). Nur zusammen mit `gleichstand_danach` |
| `gleichstand_danach` | Kriterien ab Platz N+1; leere Liste = gleicher Platz. Nur zusammen mit `gleichstand_bis_platz` |
| `abzug_je_voller_sekunde_ueber_sollzeit` | Ringabzug je voller Sekunde über `sollzeit_s` |
| `min_teilergebnis` | Untergrenze je Teilergebnis vor dem Addieren (Mehrdistanz: 0) |
| `zeit_rundung` | `summe_abrunden`: Summe der Serienzeiten wird vor dem Abzug auf volle Sekunden abgerundet (Speed) |
| `unbeendete_serie` | `ringe_bis_dahin_zeit_letzter_schuss`: Bei einer nicht beendeten Serie zählen die bis dahin erzielten Ringe und die Zeit des letzten Schusses (Speed) |

Im Turnier lassen sich alle Werte überschreiben. Der Katalog liefert nur die Vorgaben.

## Wettbewerbsklassen

`<verband>/klassen.yaml` listet die Klassen eines Verbands. Die App speichert kein Geburtsdatum und kein Geburtsjahr. Die Klasse wird bei der Anmeldung von Hand gewählt. Altersangaben sind deshalb nur Hilfetext.

```yaml
schema: 1
verband: "bds"
quelle: { regelwerk: "…", stand: "2026-06-30", abschnitte: ["A 3.08"] }
geprueft: false
klassen:
  - id: "senioren"              # eindeutig in der Datei
    name: "Seniorenklasse"
    kurz: "Sen"
    geschlecht: "maennlich"     # alle | weiblich | maennlich | divers
    alter_hilfe: "mind. 60 zu Beginn des Sportjahres, bis zum Sportjahr, in dem er 70 wird"
    mindeststarter_dm: 5
    zusammenlegen_in: ["alters", "schuetzen"]   # Reihenfolge, falls die Klasse nicht zustande kommt
```

Optionale Felder: `zusammenlegen_nach_alter: true` (die Zielklasse aus `zusammenlegen_in` richtet sich nach dem Alter, nicht nach der Reihenfolge), `hinweis`. Auf Dateiebene: `stichtag` (Sportjahr und Bezugspunkt der Altersangaben), `regeln` (allgemeine Hinweise) und `unsicher` (Punkte, die in der Quelle nicht eindeutig sind).

Für Verbände mit offiziellen Klassennummern (DSB) gibt es zusätzlich:

| Feld | Bedeutung |
|---|---|
| `nummer` | offizielle Klassennummer als Text, z. B. `"10"` für Herren I. Nur innerhalb eines Klassensatzes eindeutig. |
| `satz` | Klassensatz, z. B. `sportschiessen`, `auflage`, `bogen`. Jeder Satz muss auf Dateiebene unter `klassensaetze` beschrieben sein. |
| `hoeher_in` | Klassen, in die gemeldet werden darf, obwohl das Alter eine andere ergibt (Höhermeldung) |

## Startrecht

`<verband>/startrecht.yaml` hält fest, welche Klassen in welchem Wettbewerb starten, so wie es die Meisterschaftstabelle des Verbands vorgibt. Alle Klassen stehen als Klassennummer innerhalb des Satzes.

```yaml
schema: 1
verband: "dsb"
stand_tabelle: "DM 2025–2028"
startrecht:
  "1.10":
    satz: "sportschiessen"
    wettbewerb: "Luftgewehr"
    einzel: ["20", "21", "30", "31"]
    mannschaft: ["20", "30"]
    startet_bei: { "17": "15" }              # Einzel: Klasse 17 schießt in Klasse 15 mit
    mannschaft_startet_bei: { "12": "10" }   # Mannschaft: Klasse 12 schießt in Klasse 10 mit
    kein_startrecht: ["42", "43"]
```

Weitere Felder: `kennziffer` (wenn der Schlüssel von der Kennziffer abweicht, z. B. `"para-1.10"`), `meisterschaft`, `olympisch`, `startmoeglichkeit_0711` (Start in einer ausgeschriebenen Klasse über die Höhermeldung), `endkampf`, `mix_team` (Liste mit `name` und `klassen`), `neu_bei_dm`, `deutsche_schuelermeisterschaft` (eigene Einträge mit denselben Feldern), `hinweis` und `offen` (in der Quelle nicht eindeutig lesbar). `satz` darf eine Liste sein. Dann gilt für eine Nummer der erste Satz, der sie kennt.

## Regeln für Beiträge

- Nur Fakten eintragen: Kennziffer, Name, Schusszahlen, Zeiten. Keine Regeltexte oder Tabellen aus Sporthandbüchern kopieren.
- Bei jeder Änderung die Quelle im Pull Request nennen (Regelwerk, Fassung, Abschnitt).
- `geprueft: true` nur setzen, wenn die Gruppe vollständig mit dem aktuellen Sporthandbuch abgeglichen wurde.
- Kennziffern sind Text, keine Zahlen (`"1001"`, `"1.10"`).
- Ein neuer Verband bekommt ein eigenes Verzeichnis mit eigener `katalog.yaml`.

## Haftung

Der Katalog ist eine Arbeitshilfe von Freiwilligen. Maßgeblich ist immer das aktuelle Regelwerk des jeweiligen Verbands.
