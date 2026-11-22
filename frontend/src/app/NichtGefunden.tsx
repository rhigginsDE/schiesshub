import { Button } from "@mantine/core";
import { Link } from "@tanstack/react-router";
import { MapPinOff } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Leerzustand } from "../components/Zustand";
import { seitentitel } from "./seitentitel";

export function NichtGefunden() {
  const { t } = useTranslation();
  const titel = seitentitel([t("nicht_gefunden.titel")], t("shell:seitentitel.marke"));
  useEffect(() => {
    const vorher = document.title;
    document.title = titel;
    return () => {
      document.title = vorher;
    };
  }, [titel]);
  return (
    <div className="panel">
      <Leerzustand
        icon={MapPinOff}
        titel={t("nicht_gefunden.titel")}
        text={t("nicht_gefunden.text")}
        ueberschrift="h1"
      >
        <Button component={Link} to="/" variant="default">
          {t("aktion.zur_startseite")}
        </Button>
      </Leerzustand>
    </div>
  );
}
