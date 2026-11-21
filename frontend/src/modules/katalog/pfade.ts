export const KATALOG_PFAD = "/turnier/katalog";
export const DISZIPLIN_PFAD = "/turnier/katalog/$verband/$kennziffer";

/** Filter der Katalogseite; stehen in der Adresse, damit Links und „Zurück“ funktionieren. */
export interface KatalogSuche {
  verband?: string;
  gruppe?: string;
  q?: string;
}

/** Die Disziplin, deren Detailansicht offen ist. */
export interface KatalogAuswahl {
  verband: string;
  kennziffer: string;
}
