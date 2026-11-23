import { useLocalStorage } from "@mantine/hooks";
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { turnierListeAbfrage } from "../modules/turnier/abfragen";
import type { Turnier } from "../modules/turnier/typen";

/** Gerätespeicher: nur die ID des gewählten Turniers, nie Namen. */
export const TURNIER_SPEICHER = "schiesshub.turnier";

/**
 * Merkt ein Turnier als Wahl dieses Geräts, auch außerhalb von `useAktivesTurnier` (z. B. direkt
 * nach dem Anlegen). Offene Stationen im selben Fenster übernehmen die Wahl sofort.
 */
export function merkeTurnier(id: string): void {
  try {
    window.localStorage.setItem(TURNIER_SPEICHER, JSON.stringify(id));
  } catch {
    return;
  }
  // Dasselbe Ereignis, mit dem `useLocalStorage` (Mantine) Hooks im selben Fenster abgleicht.
  window.dispatchEvent(
    new CustomEvent("mantine-local-storage", { detail: { key: TURNIER_SPEICHER, value: id } }),
  );
}

const STATUS_RANG: Record<Turnier["status"], number> = { active: 0, draft: 1, closed: 2 };

/**
 * Aktive zuerst, dann Entwürfe, dann abgeschlossene; je Gruppe das jüngste Datum zuerst. Das
 * Übungsturnier steht ganz unten, damit niemand es am Turniertag versehentlich wählt.
 */
export function sortiereTurniere(turniere: readonly Turnier[]): Turnier[] {
  return [...turniere].sort(
    (a, b) =>
      Number(Boolean(a.is_practice)) - Number(Boolean(b.is_practice)) ||
      STATUS_RANG[a.status] - STATUS_RANG[b.status] ||
      b.date_from.localeCompare(a.date_from) ||
      a.name.localeCompare(b.name, "de"),
  );
}

export interface TurnierBestimmung {
  turnier: Turnier | null;
  /** Ohne gespeicherte Wahl genommen, weil es genau ein aktives Turnier gibt */
  automatisch: boolean;
}

/**
 * Welches Turnier die Station bearbeitet: die gespeicherte Wahl, solange es das Turnier gibt;
 * sonst das einzige aktive echte Turnier (das Übungsturnier wird nie von selbst gewählt). Gibt es
 * keins oder mehrere, muss gewählt werden (`null`).
 */
export function bestimmeTurnier(
  turniere: readonly Turnier[],
  gespeichertId: string | null,
): TurnierBestimmung {
  const gespeichert = gespeichertId ? turniere.find((t) => t.id === gespeichertId) : undefined;
  if (gespeichert) return { turnier: gespeichert, automatisch: false };
  const aktive = turniere.filter((t) => t.status === "active" && !t.is_practice);
  if (aktive.length === 1) return { turnier: aktive[0] ?? null, automatisch: true };
  return { turnier: null, automatisch: false };
}

export interface AktivesTurnier {
  /** Gewähltes Turnier; `null`, solange gewählt werden muss oder geladen wird */
  turnier: Turnier | null;
  /** Alle Turniere zur Auswahl, aktive zuerst */
  turniere: Turnier[];
  abfrage: UseQueryResult<Turnier[]>;
  automatisch: boolean;
  /** Die Auswahl ist offen (nichts gewählt oder „wechseln“ gedrückt) */
  auswahlOffen: boolean;
  waehlen: (id: string) => void;
  /** Öffnet die Auswahl; das bisherige Turnier bleibt, bis ein anderes gewählt ist */
  wechseln: () => void;
  /** Schließt eine mit „wechseln“ geöffnete Auswahl wieder */
  abbrechen: () => void;
}

/**
 * Das Turnier, in dem eine Station arbeitet (Anmeldung, Erfassung, Stand, Anzeige).
 * Die Wahl gilt je Gerät und steht im Browser-Speicher (nur die ID).
 */
export function useAktivesTurnier(): AktivesTurnier {
  const abfrage = useQuery(turnierListeAbfrage());
  const [gespeichert, setGespeichert] = useLocalStorage<string | null>({
    key: TURNIER_SPEICHER,
    defaultValue: null,
    getInitialValueInEffect: false,
  });
  const [wechselOffen, setWechselOffen] = useState(false);

  const turniere = useMemo(() => sortiereTurniere(abfrage.data ?? []), [abfrage.data]);
  const { turnier, automatisch } = bestimmeTurnier(turniere, gespeichert);

  const waehlen = useCallback(
    (id: string) => {
      setGespeichert(id);
      setWechselOffen(false);
    },
    [setGespeichert],
  );
  const wechseln = useCallback(() => setWechselOffen(true), []);
  const abbrechen = useCallback(() => setWechselOffen(false), []);

  return {
    turnier,
    turniere,
    abfrage,
    automatisch,
    auswahlOffen: abfrage.isSuccess && (turnier === null || wechselOffen),
    waehlen,
    wechseln,
    abbrechen,
  };
}
