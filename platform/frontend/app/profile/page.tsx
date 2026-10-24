"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Bot, KeyRound, Palette, UserRound } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { updateStoredUser, useUser } from "@/lib/auth";
import ThemeToggle from "@/components/theme-toggle";
import PageHeader from "@/components/ui/page-header";
import { useLanguage } from "@/lib/language";

function SectionLabel({ icon: Icon, children }: { icon: typeof UserRound; children: React.ReactNode }) {
  return (
    <h2 className="eyebrow flex items-center gap-2 text-muted">
      <Icon size={14} className="text-primary-ink" aria-hidden />
      {children}
    </h2>
  );
}

export default function ProfilePage() {
  const user = useUser();
  const { t } = useLanguage();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSaved, setPasswordSaved] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
    }
  }, [user]);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError("");
    setProfileSaved(false);
    setProfileBusy(true);
    try {
      const updated = await api.updateProfile({ email, name });
      updateStoredUser(updated);
      setProfileSaved(true);
    } catch (err) {
      setProfileError(
        err instanceof ApiError && err.status === 409 ? t("profile.error.emailTaken") : t("profile.error.saveFailed")
      );
    } finally {
      setProfileBusy(false);
    }
  };

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSaved(false);
    if (newPassword !== confirmPassword) {
      setPasswordError(t("profile.error.passwordMismatch"));
      return;
    }
    setPasswordBusy(true);
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      setPasswordSaved(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // The backend returns 401 both for a dead session and for a wrong
        // current password (`platform/auth/router.py:339`). Probe `/api/auth/me`
        // to tell them apart: if the session is still alive, this 401 must
        // have meant "wrong current password". If the probe itself 401s,
        // `handle()` has already redirected — the session really was dead.
        try {
          await api.me();
          setPasswordError(t("profile.error.currentPasswordIncorrect"));
        } catch (probeErr) {
          if (probeErr instanceof ApiError && probeErr.status === 401) {
            // Session dead; handle() already redirected. No inline error.
          } else {
            setPasswordError(t("profile.error.passwordChangeFailed"));
          }
        }
      } else {
        setPasswordError(t("profile.error.passwordChangeFailed"));
      }
    } finally {
      setPasswordBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <PageHeader eyebrow={t("profile.eyebrow")} title={t("profile.title")} subtitle={t("profile.subtitle")} />

      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <SectionLabel icon={Palette}>{t("profile.appearance")}</SectionLabel>
          <ThemeToggle />
        </div>
      </div>

      <Link
        href="/preferences"
        className="tap card flex flex-wrap items-center justify-between gap-x-3 gap-y-1 transition-colors duration-normal hover:bg-surface"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Bot size={16} className="shrink-0 text-primary-ink" aria-hidden />
          <span className="font-semibold text-ink">{t("profile.automationPreferences")}</span>
        </span>
        <span className="flex min-w-0 shrink-0 items-center gap-1.5 text-sm text-muted">
          {t("profile.automationPreferencesHint")}
          <ArrowRight size={13} className="shrink-0 -rotate-45" aria-hidden />
        </span>
      </Link>

      <form onSubmit={saveProfile} className="card space-y-4">
        <SectionLabel icon={UserRound}>{t("profile.accountDetails")}</SectionLabel>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("profile.fullName")}</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={1}
            maxLength={120}
            className="input"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("profile.email")}</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="input"
          />
        </div>
        {profileError && <p className="text-sm text-danger">{profileError}</p>}
        {profileSaved && <p className="text-sm text-success">{t("profile.updated")}</p>}
        <button type="submit" disabled={profileBusy} className="btn-primary">
          {profileBusy ? t("profile.saving") : t("profile.saveChanges")}
        </button>
      </form>

      <form onSubmit={savePassword} className="card space-y-4">
        <SectionLabel icon={KeyRound}>{t("profile.changePassword")}</SectionLabel>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("profile.currentPassword")}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="input"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("profile.newPassword")}</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            placeholder={t("profile.newPasswordPlaceholder")}
            className="input"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">{t("profile.confirmNewPassword")}</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
            className="input"
          />
        </div>
        {passwordError && <p className="text-sm text-danger">{passwordError}</p>}
        {passwordSaved && <p className="text-sm text-success">{t("profile.passwordChanged")}</p>}
        <button type="submit" disabled={passwordBusy} className="btn-primary">
          {passwordBusy ? t("profile.saving") : t("profile.changePassword")}
        </button>
      </form>
    </div>
  );
}
