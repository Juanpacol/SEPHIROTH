"use client";

/** English or Spanish, on its own: the landing page has no theme to choose, so the control that used to share
 * a pill with the theme buttons is just this. Both languages are shown and the one in use is lit; pressing it
 * switches. */
import { useLanguage } from "@/lib/language";

export default function LanguageSwitch({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useLanguage();
  const option = (code: "en" | "es") => (
    <span
      className={`transition-colors duration-normal ease-standard ${
        lang === code ? "text-ink" : "text-muted"
      }`}
    >
      {code.toUpperCase()}
    </span>
  );
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "es" : "en")}
      aria-label={t("common.toggleLanguage")}
      title={lang === "en" ? "English" : "Español"}
      className={`tap inline-flex items-center gap-1.5 rounded-full px-2 font-mono text-[11px] font-semibold tracking-[0.18em] hover:text-ink ${className}`}
    >
      {option("en")}
      <span aria-hidden="true" className="text-muted/60">
        /
      </span>
      {option("es")}
    </button>
  );
}
