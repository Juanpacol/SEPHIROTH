"use client";

/** Language state: "en" | "es", localStorage-backed — mirrors lib/theme.ts.
 * Unlike theme (a CSS class toggle), translated text needs every mounted
 * component to re-render on change, so this is a React context instead of
 * a bare hook.
 *
 * The dictionaries themselves live in `lib/i18n/dictionaries.{en,es}.ts` —
 * split out so this file stays small as the app's translation coverage
 * grows; both language files share one flat key space (`scope.section.
 * element`), so there's no "which dictionary wins" ambiguity to reason
 * about at a call site. */

import { createContext, useContext, useEffect, useState } from "react";
import EN from "./i18n/dictionaries.en";
import ES from "./i18n/dictionaries.es";

export type Lang = "en" | "es";

const LANG_KEY = "cac_lang";

const DICTIONARIES: Record<Lang, Record<string, string>> = { en: EN, es: ES };

export function getLanguage(): Lang {
  if (typeof window === "undefined") return "en";
  return (localStorage.getItem(LANG_KEY) as Lang | null) ?? "en";
}

/** Maps our short codes to the words the LLM system prompt needs. */
export function languageName(lang: Lang): string {
  return lang === "es" ? "Spanish" : "English";
}

interface LanguageContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(getLanguage());
  }, []);

  const setLang = (next: Lang) => {
    localStorage.setItem(LANG_KEY, next);
    setLangState(next);
  };

  const t = (key: string): string => {
    const value = DICTIONARIES[lang][key] ?? DICTIONARIES.en[key];
    if (value === undefined) {
      // A key missing from BOTH dictionaries renders as this raw string on
      // screen — easy to miss during a large migration, so flag it loudly
      // in dev instead of relying on catching it by eye.
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[i18n] missing translation key: "${key}"`);
      }
      return key;
    }
    return value;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}
