"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { homeFor, storeAuth } from "@/lib/auth";
import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res =
        mode === "login"
          ? await api.login({ email, password })
          : await api.register({ email, name, password });
      storeAuth(res.access_token, res.user);
      router.push(homeFor(res.user.role));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      if (message.includes("409")) setError(t("login.error.emailTaken"));
      else if (message.includes("401")) setError(t("login.error.invalidCredentials"));
      else if (message.includes("422")) setError(t("login.error.validation"));
      else setError(t("login.error.serverUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
            <WingMark size={20} />
          </span>
          <span className="text-lg font-bold tracking-tight">SEPHIROTH</span>
        </div>

        <Link href="/" className="mb-2 block text-center text-sm font-medium text-muted hover:text-primary">
          {t("login.backToHome")}
        </Link>

        <form onSubmit={submit} className="card space-y-4">
          <div>
            <h1 className="font-extrabold">
              {mode === "login" ? t("login.welcomeBack") : t("login.createAccount")}
            </h1>
            <p className="text-sm text-muted">
              {mode === "login" ? t("login.signInSubtitle") : t("login.registerSubtitle")}
            </p>
          </div>

          {mode === "register" && (
            <div>
              <label className="mb-1 block text-sm font-semibold">{t("login.fullName")}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder={t("login.fullNamePlaceholder")}
                className="input"
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-semibold">{t("login.email")}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@hospital.org"
              className="input"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold">{t("login.password")}</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder={t("login.passwordPlaceholder")}
              className="input"
            />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy ? t("login.pleaseWait") : mode === "login" ? t("login.signIn") : t("login.createAccountButton")}
          </button>

          <p className="text-center text-sm text-muted">
            {mode === "login" ? t("login.noAccountYet") : t("login.alreadyRegistered")}{" "}
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="font-semibold text-primary"
            >
              {mode === "login" ? t("login.registerAsClinician") : t("login.signIn")}
            </button>
          </p>
        </form>

        <p className="mt-4 text-center text-sm text-muted">
          {t("login.claimPrompt")}{" "}
          <Link href="/portal/claim" className="font-semibold text-primary">
            {t("login.claimLink")}
          </Link>
        </p>

        <p className="mt-4 text-center text-xs text-muted">{t("common.disclaimer")}</p>
      </div>
    </div>
  );
}
