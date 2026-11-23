import type { Abschnitt } from "../../api/typen";

/** Eine Position eines Abschnitts, z. B. „Pos. 6, 15 m, kniend beidhändig oder stehend schwache Hand“. */
export type Position = NonNullable<Abschnitt["positionen"]>[number];

type AnschlagApi = Position["anschlaege"][number];

/** Haltung; „sitzend“ kommt mit dem DSB-Katalog (Auflage) hinzu. */
export type Haltung = AnschlagApi["haltung"] | "sitzend";

/** Eine erlaubte Anschlag-Alternative einer Position. */
export type Anschlag = Omit<AnschlagApi, "haltung"> & {
  haltung: Haltung;
  /** Auflageschießen: Die Waffe liegt auf einer Auflage. */
  aufgelegt?: boolean | null;
};

export type Hand = NonNullable<AnschlagApi["hand"]>;
