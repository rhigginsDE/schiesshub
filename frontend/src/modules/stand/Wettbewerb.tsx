import s from "./stand.module.css";

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
