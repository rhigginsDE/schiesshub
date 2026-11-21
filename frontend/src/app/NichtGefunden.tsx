import { Button } from "@mantine/core";
import { Link } from "@tanstack/react-router";
import { MapPinOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Leerzustand } from "../components/Zustand";

export function NichtGefunden() {
  const { t } = useTranslation();
  return (
    <div className="panel">
      <Leerzustand
        icon={MapPinOff}
        titel={t("nicht_gefunden.titel")}
        text={t("nicht_gefunden.text")}
      >
        <Button component={Link} to="/" variant="default">
          {t("aktion.zur_startseite")}
        </Button>
      </Leerzustand>
    </div>
  );
}
