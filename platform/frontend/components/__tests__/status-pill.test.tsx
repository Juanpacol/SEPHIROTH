import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import StatusPill from "@/components/status-pill";
import { LanguageProvider } from "@/lib/language";

function renderPill(label: string, lang: "en" | "es") {
  localStorage.setItem("cac_lang", lang);
  return render(
    <LanguageProvider>
      <StatusPill label={label} />
    </LanguageProvider>
  );
}

describe("StatusPill", () => {
  afterEach(() => localStorage.removeItem("cac_lang"));

  it("follows the active language for severity and risk level", () => {
    renderPill("critical", "es");
    expect(screen.getByText("Crítico")).toBeInTheDocument();
  });

  it("translates the composite risk label the critical-patients list sends", () => {
    renderPill("high risk", "es");
    expect(screen.getByText("Riesgo alto")).toBeInTheDocument();
  });

  it("keeps English when English is active", () => {
    renderPill("medium risk", "en");
    expect(screen.getByText("Medium risk")).toBeInTheDocument();
  });

  it("shows an unknown status as-is instead of a raw i18n key", () => {
    renderPill("superseded", "es");
    expect(screen.getByText("superseded")).toBeInTheDocument();
    expect(screen.queryByText(/status\./)).not.toBeInTheDocument();
  });
});
