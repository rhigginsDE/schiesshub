<p align="center">
  <img src="public/logo.png" alt="Schiesshub Logo" width="200">
</p>

# Schiesshub

Open-Source-Software, mit der Schießvereine Turniere und Vereinsmeisterschaften am Wettkampftag abwickeln: anmelden, Ergebnisse erfassen, Ranglisten zeigen.

> 🚧 Frühe Entwicklung. Noch nicht für echte Wettkämpfe geeignet.

## So ist es gedacht

Ein kleiner Linux-Rechner steht im Schützenhaus und ist der Server. Laptops, Tablets und Handys verbinden sich per WLAN und öffnen die App im Browser. Internet ist nicht nötig.

| Station | Aufgabe |
|---|---|
| Anmeldung | Teilnehmer erfassen, Starts buchen |
| Turnier | Wettbewerbe aus dem Disziplin-Katalog zusammenstellen, Regeln einstellen |
| Erfassung | Ergebnisse je Start eingeben |
| Anzeige | Startliste, Live-Wertung und Siegerliste am Bildschirm des Servers |
| System | Sicherung auf USB-Stick, Geräte, Rollen |

Alles ist einstellbar. Disziplinen liegen als Dateien im [Disziplin-Katalog](catalog/README.md) und werden beim Start eingelesen. Den Anfang machen die Disziplinen des BDS.

## Dokumentation

- [Architektur](docs/ARCHITEKTUR.md)
- [Roadmap und geplante Module](docs/ROADMAP.md)
- [Disziplin-Katalog pflegen](catalog/README.md)

## Entwicklung

Voraussetzungen: Docker, Node.js und pnpm.

```bash
cp .env.example .env
docker compose up -d --build     # Datenbank und Backend
cd frontend && pnpm install && pnpm dev   # Oberfläche mit Hot Reload
```

Details stehen in `backend/README.md` und `frontend/README.md`.

## Mitwirken

Beiträge sind willkommen, besonders Korrekturen am Disziplin-Katalog. Siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Lizenz

- Quellcode: [GNU AGPL-3.0](LICENSE)
- Disziplin-Katalog (`catalog/`): [CC0 1.0](catalog/LICENSE)
- **Name und Logo** „Schiesshub“ sind nicht Teil dieser Lizenzen, siehe [TRADEMARKS.md](TRADEMARKS.md). Forks dürfen den Code nutzen, aber nicht unter dem Namen oder Logo Schiesshub auftreten.

Schiesshub ist ein Freiwilligenprojekt ohne Gewähr. Maßgeblich sind immer die Regelwerke der Verbände.
