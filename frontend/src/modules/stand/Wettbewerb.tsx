import type { TurnierUebersicht } from "../turnier/typen";
import s from "./stand.module.css";

/** Kennziffer je Wettbewerb (ID → `catalog_code`), für Starts, die nur Name und ID mitbringen. */
export type Kennziffern = ReadonlyMap<string, string | null>;

export function kennziffernAus(uebersicht: Pick<TurnierUebersicht, "competitions">): Kennziffern {
  return new Map(uebersicht.competitions.map((w) => [w.id, w.catalog_code ?? null]));
}

/**
 * Wettbewerb als Text mit Kennziffer davor („1001 Pistole bis 9 mm“): Zwei Wettbewerbe können
 * gleich heißen (1001 und 1201), unterscheidbar sind sie nur an der Kennziffer.
 */
export function wettbewerbText(code: string | null | undefined, name: string): string {
  return code ? `${code} ${name}` : name;
}

/** Wettbewerb mit der Kennziffer in Mono davor, wie im Turnier-Editor. */
export function WettbewerbName({ code, name }: { code: string | null | undefined; name: string }) {
  return (
    <span className={s.wettbewerb}>
      {code && <span className={`num ${s.kennziffer}`}>{code}</span>}
      <span>{name}</span>
    </span>
  );
}
