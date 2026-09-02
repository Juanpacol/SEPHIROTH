"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getStoredUser, homeFor, storeAuth } from "@/lib/auth";
import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";

export default function ClaimInvitePage() {
  return (
    <Suspense fallback={null}>
      <ClaimInviteForm />
    </Suspense>
  );
}

function ClaimInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLanguage();
  // The raw "{invite_id}.{secret}" code is meaningless to a patient asked
  // to paste it in by hand — it travels silently in the invite link's
  // query param instead (see app/patients/[id]/page.tsx's invite button),
  // never shown or typed. A patient who opens this page without that
  // param has an incomplete/broken link, not a code to enter.
  const code = searchParams.get("code") ?? "";
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Mirrors AuthGuard's "don't render until we know" pattern — a patient
  // who already claimed this invite (or is otherwise logged in) and
  // reopens the same link should land back in their portal without a
  // flash of a dead-end form with no way back, which is what happened
  // before this check existed at all.
  const [redirecting, setRedirecting] = useState(true);

  useEffect(() => {
    const user = getStoredUser();
    if (user) {
      router.replace(homeFor(user.role));
      return;
    }
    setRedirecting(false);
  }, [router]);

  if (redirecting) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.claimInvite({ code: code.trim(), email, name, password });
      storeAuth(res.access_token, res.user);
      router.push(homeFor(res.user.role));
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(t("portal.claim.error.invalidInvite"));
      } else if (err instanceof ApiError && err.status === 409) {
        setError(t("portal.claim.error.emailTaken"));
      } else if (err instanceof ApiError && err.status === 422) {
        setError(t("portal.claim.error.validation"));
      } else {
        setError(t("portal.claim.error.serverUnreachable"));
      }
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

        {!code ? (
          <div className="card space-y-3 text-center">
            <h1 className="font-extrabold">{t("portal.claim.incompleteTitle")}</h1>
            <p className="text-sm text-muted">{t("portal.claim.incompleteBody")}</p>
            <p className="text-sm text-muted">
              {t("portal.claim.alreadyHaveAccount")}{" "}
              <Link href="/login" className="font-semibold text-primary">{t("portal.claim.signIn")}</Link>
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="card space-y-4">
            <div>
              <h1 className="font-extrabold">{t("portal.claim.setupTitle")}</h1>
              <p className="text-sm text-muted">{t("portal.claim.setupBody")}</p>
            </div>

            <div>
              <label className="mb-1 block text-sm font-semibold">{t("portal.claim.fullName")}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder={t("portal.claim.fullNamePlaceholder")}
                className="input"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-semibold">{t("portal.claim.email")}</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.org"
                className="input"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-semibold">{t("portal.claim.password")}</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder={t("portal.claim.passwordPlaceholder")}
                className="input"
              />
            </div>

            {error && <p className="text-sm text-danger">{error}</p>}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-primary py-2.5 text-sm font-semibold text-white disabled:opacity-40"
            >
              {busy ? t("portal.claim.pleaseWait") : t("portal.claim.submit")}
            </button>

            <p className="text-center text-sm text-muted">
              {t("portal.claim.alreadyHaveAccount")}{" "}
              <Link href="/login" className="font-semibold text-primary">{t("portal.claim.signIn")}</Link>
            </p>
          </form>
        )}

        <p className="mt-4 text-center text-xs text-muted">{t("common.disclaimer")}</p>
      </div>
    </div>
  );
}
