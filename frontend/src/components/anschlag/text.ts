import type { TFunction } from "i18next";
import type { Anschlag, Position } from "./typen";

/** „stehend, nur schwache Hand“ – Haltung und, falls vorgegeben, Hand. */
export function anschlagText(anschlag: Anschlag, t: TFunction<"katalog">): string {
  const haltung = t(`anschlag.haltung.${anschlag.haltung}`);
  return anschlag.hand ? `${haltung}, ${t(`anschlag.hand.${anschlag.hand}`)}` : haltung;
}

/** Alle erlaubten Anschläge einer Position: „kniend, beidhändig oder stehend, nur schwache Hand“. */
export function positionAnschlagText(position: Position, t: TFunction<"katalog">): string {
  return position.anschlaege
    .map((anschlag) => anschlagText(anschlag, t))
    .join(` ${t("anschlag.oder")} `);
}
