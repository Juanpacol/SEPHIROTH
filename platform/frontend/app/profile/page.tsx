"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot } from "lucide-react";
import { api } from "@/lib/api";
import { updateStoredUser, useUser } from "@/lib/auth";
import ThemeToggle from "@/components/theme-toggle";

export default function ProfilePage() {
  const user = useUser();
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
      const message = err instanceof Error ? err.message : "Request failed";
      setProfileError(message.includes("409") ? "That email is already registered." : "Could not save changes.");
    } finally {
      setProfileBusy(false);
    }
  };

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");
    setPasswordSaved(false);
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords don't match.");
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
      const message = err instanceof Error ? err.message : "Request failed";
      setPasswordError(message.includes("401") ? "Current password is incorrect." : "Could not change password.");
    } finally {
      setPasswordBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-xl font-extrabold">Profile</h1>
        <p className="text-sm text-muted">Manage your account and appearance preferences.</p>
      </div>

      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-bold">Appearance</h2>
          <ThemeToggle />
        </div>
      </div>

      <Link href="/preferences" className="card flex items-center justify-between hover:bg-surface">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-primary" />
          <span className="font-bold">Automation preferences</span>
        </div>
        <span className="text-sm text-muted">Reminder timing, quiet hours →</span>
      </Link>

      <form onSubmit={saveProfile} className="card space-y-4">
        <h2 className="font-bold">Account details</h2>
        <div>
          <label className="mb-1 block text-sm font-semibold">Full name</label>
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
          <label className="mb-1 block text-sm font-semibold">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="input"
          />
        </div>
        {profileError && <p className="text-sm text-danger">{profileError}</p>}
        {profileSaved && <p className="text-sm text-success">Profile updated.</p>}
        <button type="submit" disabled={profileBusy} className="btn-primary">
          {profileBusy ? "Saving…" : "Save changes"}
        </button>
      </form>

      <form onSubmit={savePassword} className="card space-y-4">
        <h2 className="font-bold">Change password</h2>
        <div>
          <label className="mb-1 block text-sm font-semibold">Current password</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="input"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">New password</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            placeholder="At least 8 characters"
            className="input"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-semibold">Confirm new password</label>
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
        {passwordSaved && <p className="text-sm text-success">Password changed.</p>}
        <button type="submit" disabled={passwordBusy} className="btn-primary">
          {passwordBusy ? "Saving…" : "Change password"}
        </button>
      </form>
    </div>
  );
}
