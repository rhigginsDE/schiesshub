import type { Abschnitt } from "../../api/typen";

/** Eine Position eines Abschnitts, z. B. „Pos. 6, 15 m, kniend beidhändig oder stehend schwache Hand“. */
export type Position = NonNullable<Abschnitt["positionen"]>[number];

/** Eine erlaubte Anschlag-Alternative einer Position. */
export type Anschlag = Position["anschlaege"][number];

export type Haltung = Anschlag["haltung"];

export type Hand = NonNullable<Anschlag["hand"]>;
