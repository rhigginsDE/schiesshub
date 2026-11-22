# Schiesshub Frontend

Oberfläche von Schiesshub: React, TypeScript, Vite, Mantine. Läuft im Browser der Stationen und spricht mit dem Backend unter `/api/v1`. Zur Laufzeit wird nichts aus dem Internet geladen; Schriften und Symbole liegen im Paket.

## Starten

Voraussetzung: Node 22 oder neuer, pnpm 10.

```sh
pnpm install
pnpm dev
```

Die Oberfläche läuft dann unter <http://localhost:5180>. Anfragen an `/api` gehen an das Backend unter `http://localhost:8010`. Läuft das Backend nicht, zeigt die Kopfzeile „Keine Verbindung“ und die Seiten sagen, was fehlt.

## Befehle

| Befehl            | Zweck                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| `pnpm dev`        | Entwicklungsserver mit Hot Reload (Port 5180)                                                    |
| `pnpm build`      | Typprüfung und Produktions-Build nach `dist/`                                                    |
| `pnpm typecheck`  | nur Typprüfung                                                                                   |
| `pnpm test`       | Tests einmal ausführen (Vitest, Testing Library)                                                 |
| `pnpm test:watch` | Tests im Beobachtungsmodus                                                                       |
| `pnpm lint`       | Biome: Format und Regeln prüfen                                                                  |
| `pnpm format`     | Biome: Format und sichere Korrekturen anwenden                                                   |
| `pnpm gen:api`    | Typen aus der OpenAPI-Beschreibung des laufenden Backends nach `src/api/schema.gen.ts` schreiben |

`pnpm gen:api` braucht das laufende Backend und einmalig Zugriff auf die npm-Registry: Der Generator (`openapi-typescript`) läuft über `pnpm dlx` mit eigenem TypeScript 5, weil er TypeScript 7 noch nicht unterstützt. Die erzeugte Datei wird eingecheckt.

## Aufbau

```text
src/
  api/        fetch-Wrapper, Abfragen (TanStack Query), SSE-Hook, erzeugte Typen
  app/        App-Shell, Startseite, Router, Modul-Vertrag, Serverstatus
  components/ Bausteine, die mehrere Module nutzen (Chip, Kachel, Lade-/Leer-/Fehlerzustand)
  i18n/       Einrichtung von i18next
  lib/        Hilfsfunktionen, z. B. Zahlen- und Zeitformat
  locales/    Sprachdateien: locales/<sprache>/<namensraum>.json
  modules/    ein Ordner je Modul
  theme/      Farben, Schriften, Mantine-Theme, CSS-Variablen
  test/       Testeinrichtung und Hilfen
```

- **Theme:** `theme/tokens.ts` ist die einzige Quelle für Farben. Daraus entstehen das Mantine-Theme und die CSS-Variablen `--sh-*` für hell und dunkel. In CSS nur diese Variablen verwenden, keine festen Farbwerte. Ein Test prüft die Kontraste beider Farbschemata.
- **Texte:** Jeder sichtbare Text steht in `locales/de/*.json`. Eine weitere Sprache ist ein weiterer Ordner mit denselben Dateien.
- **Zahlen:** Über `lib/format.ts` ausgeben (Dezimalkomma nach aktiver Sprache) und mit der Klasse `num` auszeichnen (feste Ziffernbreite).
- **Daten:** Abfragen stehen in `api/abfragen.ts`. Der Server meldet Änderungen über `GET /api/v1/events`; Module tragen im Manifest ein, welche Daten nach welchem Ereignis neu geladen werden.

## Ein Modul anlegen

Ein Modul ist ein Ordner unter `src/modules/<name>/` mit eigenen Routen, Komponenten und einer Sprachdatei. Die App-Shell baut Navigation, Kacheln und Routen aus der Modul-Liste.

1. **Sprachdatei** `src/locales/de/<name>.json` mit mindestens `titel` und `zweck` (ein Satz, wofür das Modul da ist).
2. **Routen** mit `createRoute` anlegen; Eltern-Route ist `rootRoute` aus `src/app/rootRoute.ts`.
3. **Manifest** schreiben (Typ `ModulManifest` in `src/app/modul.ts`):

   ```tsx
   export const kasse: ModulManifest = {
     id: "kasse",
     namensraum: "kasse",
     // eigene Station in der Kopfzeile …
     navigation: { art: "station", pfad: "/kasse", icon: Wallet, reihenfolge: 15 },
     // … oder Bereich innerhalb einer Station:
     // navigation: { art: "bereich", station: "anmeldung", pfad: "/anmeldung/kasse", icon: Wallet, reihenfolge: 10 },
     berechtigung: "kasse.nutzen",
     routen: [kasseRoute],
     ereignisse: { "zahlung.gebucht": [["kasse"]] },
   };
   ```

4. Das Manifest in `src/modules/index.ts` in die Liste eintragen.

`berechtigung` nennt eine Berechtigung des Backends (`tournament.read`) oder eine Liste, von der eine reicht. Navigation und Kacheln zeigen nur, was die Rechte aus `GET /auth/status` erlauben (`*` und `bereich.*` werden ausgewertet).
In Komponenten: `const darfBearbeiten = useDarf("tournament.edit");` aus `src/app/berechtigungen.ts` (Knöpfe ausblenden oder sperren; der Server prüft trotzdem).
Ohne Anmeldung und solange der Server nichts durchsetzt, ist alles erlaubt; 401 und 403 behandelt die App-Shell (Anmeldung bzw. Meldung).

Als Vorlage eignen sich `modules/anmeldung` (kleinste Form) und `modules/katalog` (Routen mit Suchparametern, Abfragen, Tests).

## Layout-Regeln

- **Platz nutzen:** Seiten verwenden die ganze Bildschirmbreite. Wer lieber eine gebündelte Ansicht hat, schaltet in der Kopfzeile auf „Schmale Ansicht“; die Wahl gilt je Gerät (`src/app/seitenbreite.ts`). Weitere Ansichten je Bildschirm kommen als zusätzliche Werte derselben Einstellung dazu.
- **Kein doppelter Scroll:** Nie scrollen die Seite und ein Bereich darin gleichzeitig. Es gibt zwei Formen:
  - _Fenster-Layout_ für Arbeitsansichten mit mehreren Spalten (Liste neben Detail): Die Seite füllt genau das Fenster und scrollt selbst nicht, jede Spalte scrollt für sich. Die Seite setzt dafür `data-layout="fenster"` an ihrem Wurzelelement; Vorbild ist der Disziplin-Katalog. Greift ab 1101 px Breite und 560 px Höhe.
  - _Seiten-Layout_ für alles andere und für schmale Bildschirme: Nur die Seite scrollt, kein Bereich hat einen eigenen Scrollbalken.
- **Kein horizontaler Scroll** der Seite. Breite Tabellen brechen um oder wechseln in eine Kartenansicht.
