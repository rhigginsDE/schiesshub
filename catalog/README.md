# Disziplin-Katalog

Hier liegen die Disziplinen, die Schiesshub kennt. Der Server liest dieses Verzeichnis bei jedem Start ein. Wer eine Disziplin ergänzen oder korrigieren will, ändert eine YAML-Datei und öffnet einen Pull Request. Code muss dafür niemand anfassen.

## Aufbau

```
catalog/
  <verband>/
    katalog.yaml          Kopf: Verband, Regelwerk, Stand, Hinweise
    klassen.yaml          Wettbewerbsklassen (optional)
    gruppen/
      <gruppe>.yaml       eine Datei je Disziplingruppe
```

Aktuell enthalten: `bds/` mit 191 Disziplinen in 25 Gruppen (Sporthandbuch Teil K und L, Fassung des BVA-Genehmigungsbescheids vom 30.06.2026).

## Eine Gruppendatei

```yaml
schema: 1
verband: "bds"
gruppe:
  id: "kw-25m-praezision"       # = Dateiname
  name: "KW 25 m Präzision"
  waffenart: "kurzwaffe"        # kurzwaffe | langwaffe | flinte
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

Werte für `gruppe.art`: `praezision`, `speed`, `kombi`, `fallscheibe`, `fallscheibe-gk`, `fallscheibe-kk`, `mehrdistanz`, `zeitserie`, `fertigkeit`, `symbolscheibe`, `intervall`.

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

Bei Mehrdistanz stehen die Varianten für die Parcours-Varianten des Sporthandbuchs, nicht für Meisterschaftsebenen.

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
| `gleichstand` | Kriterien bei Ergebnisgleichheit in ihrer Reihenfolge, z. B. `zehner`, `innenzehner`, `neuner_abwaerts`, `parcours_zeit` (niedrigere Parcourszeit gewinnt). Fehlt, wenn das Sporthandbuch keine Regel nennt. |
| `abzug_je_voller_sekunde_ueber_sollzeit` | Ringabzug je voller Sekunde über `sollzeit_s` |
| `min_teilergebnis` | Untergrenze je Teilergebnis vor dem Addieren (Mehrdistanz: 0) |
| `zeit_rundung` | `summe_abrunden`: Summe der Serienzeiten wird vor dem Abzug auf volle Sekunden abgerundet (Speed) |

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

## Regeln für Beiträge

- Nur Fakten eintragen: Kennziffer, Name, Schusszahlen, Zeiten. Keine Regeltexte oder Tabellen aus Sporthandbüchern kopieren.
- Bei jeder Änderung die Quelle im Pull Request nennen (Regelwerk, Fassung, Abschnitt).
- `geprueft: true` nur setzen, wenn die Gruppe vollständig mit dem aktuellen Sporthandbuch abgeglichen wurde.
- Kennziffern sind Text, keine Zahlen (`"1001"`).
- Ein neuer Verband bekommt ein eigenes Verzeichnis mit eigener `katalog.yaml`.

## Haftung

Der Katalog ist eine Arbeitshilfe von Freiwilligen. Maßgeblich ist immer das aktuelle Regelwerk des jeweiligen Verbands.
