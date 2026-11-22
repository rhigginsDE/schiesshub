import type { components } from "../../api/schema.gen";

/** Sprechende Namen für die Typen des Backend-Moduls `anzeige` (Quelle: `schema.gen.ts`). */
type Schemas = components["schemas"];

export type Anzeige = Schemas["DisplayOut"];
export type AnzeigeKonfig = Schemas["DisplayConfig"];
export type Szene = NonNullable<AnzeigeKonfig["scenes"]>[number];
export type SzenenArt = Szene["kind"];
export type LiveSzene = Schemas["LiveRankingScene"];
export type StartlistenSzene = Schemas["StartlistScene"];
export type SiegerSzene = Schemas["WinnersScene"];
export type StandSzene = Schemas["RangeScene"];
export type HinweisSzene = Schemas["NoticeScene"];

export type Feed = Schemas["FeedOut"];
export type FeedSzene = Feed["scenes"][number];
export type FeedKopf = Schemas["FeedHeader"];
export type FeedWarnung = Schemas["FeedWarning"];
export type FeedPerson = Schemas["FeedPerson"];
export type FeedRangliste = Schemas["FeedRanking"];
export type FeedGruppe = Schemas["FeedRankGroup"];
export type FeedZeile = Schemas["FeedRankRow"];
export type FeedSerie = Schemas["SeriesPart"];
export type FeedStartliste = Schemas["FeedStartlist"];
export type FeedStand = Schemas["FeedRange"];
export type FeedAblauf = Schemas["FeedProcedure"];
export type FeedAbschnitt = Schemas["FeedSection"];
export type FeedSerienSchritt = Schemas["FeedSeriesStep"];
export type FeedPosition = Schemas["FeedPosition"];
export type FeedBahn = Schemas["FeedLane"];
export type FeedVorschauAnfrage = Schemas["FeedPreviewRequest"];

export type SzeneVon<A extends FeedSzene["kind"]> = Extract<FeedSzene, { kind: A }>;
