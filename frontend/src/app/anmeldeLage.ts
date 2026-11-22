import type { AuthStatus } from "../api/typenSystem";
import type { Rechte } from "./berechtigungen";

/** Seiten, die statt der App erscheinen, solange etwas fehlt. */
export type AnmeldeSeite = "einrichtung" | "koppeln" | "anmelden";

export interface AnmeldeLage {
  /** `GET /auth/status` läuft noch zum ersten Mal. */
  pruefe: boolean;
  /** Der Server verlangt eine Anmeldung (`auth_enforced`) oder hat mit 401 geantwortet. */
  sperren: boolean;
  /** Was als Nächstes fehlt: Ersteinrichtung, Kopplung, Anmeldung; `null` = nichts. */
  ausstehend: AnmeldeSeite | null;
  /** Diese Seite muss statt der App erscheinen; `null` = App benutzbar. */
  pflicht: AnmeldeSeite | null;
}

export interface LageEingaben {
  status: AuthStatus | undefined;
  /** `GET /auth/status` ist fehlgeschlagen (z. B. älterer Server ohne Anmeldung). */
  statusFehler: boolean;
  /** Irgendein Endpunkt hat mit 401 geantwortet, seit der Status zuletzt geladen wurde. */
  abgewiesen: boolean;
}

/**
 * Leitet aus dem Status ab, was die App zeigt. Ein einziger Schalter entscheidet über das Sperren:
 * `auth_enforced` aus dem Status oder eine 401-Antwort. Ohne ihn bleibt die App benutzbar und
 * zeigt nur einen Hinweis.
 */
export function bestimmeLage({ status, statusFehler, abgewiesen }: LageEingaben): AnmeldeLage {
  if (!status) {
    return {
      pruefe: !statusFehler,
      sperren: abgewiesen,
      ausstehend: null,
      pflicht: null,
    };
  }
  const ausstehend: AnmeldeSeite | null = status.setup_required
    ? "einrichtung"
    : !status.device
      ? "koppeln"
      : !status.role
        ? "anmelden"
        : null;
  const sperren = status.auth_enforced || abgewiesen;
  return { pruefe: false, sperren, ausstehend, pflicht: sperren ? ausstehend : null };
}

/** Rechte aus dem Status. Ohne Rolle und ohne Sperre ist alles offen. */
export function rechteAus(status: AuthStatus | undefined, lage: AnmeldeLage): Rechte {
  if (!status) return lage.sperren ? { offen: false, erlaubt: [] } : { offen: true };
  if (!status.role && !lage.sperren) return { offen: true };
  return { offen: false, erlaubt: status.permissions };
}

/**
 * Warum das Gerät nicht (mehr) hineinkommt, soweit der Server es sagt:
 * - `gesperrt`: Das Gerät wurde unter System → Geräte gesperrt.
 * - `abgelaufen`: Die Anmeldung ist abgelaufen oder wurde beendet.
 */
export type AbweisGrund = "gesperrt" | "abgelaufen";

/**
 * Grund aus `GET /auth/status` (`device_revoked`) oder dem `code` der letzten 401-Antwort
 * (`device_revoked`, `session_expired`). Ältere Server liefern beides nicht: dann `null`.
 */
export function abweisGrund(
  status: AuthStatus | undefined,
  code401: string | null | undefined,
): AbweisGrund | null {
  if (status?.device_revoked && !status.device) return "gesperrt";
  if (code401 === "device_revoked" && !status?.device) return "gesperrt";
  if (code401 === "session_expired" && !status?.user) return "abgelaufen";
  return null;
}
