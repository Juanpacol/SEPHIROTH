"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { homeFor, storeAuth } from "@/lib/auth";

export default function ClaimInvitePage() {
  const router = useRouter();
  const [code, setCode] = useState("");
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
      const res = await api.claimInvite({ code: code.trim(), email, name, password });
      storeAuth(res.access_token, res.user);
      router.push(homeFor(res.user.role));
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError("That claim code is invalid or has expired. Ask your clinician for a new one.");
      } else if (err instanceof ApiError && err.status === 409) {
        setError("That email is already registered.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Check your input (password ≥ 8 characters).");
      } else {
        setError("Could not reach the server. Is the backend running?");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-sephiroth font-extrabold text-ink/80">
            S
          </span>
          <span className="text-lg font-bold tracking-tight">SEPHIROTH</span>
        </div>

        <form onSubmit={submit} className="card space-y-4">
          <div>
            <h1 className="font-extrabold">Set up your portal account</h1>
            <p className="text-sm text-muted">
              Enter the claim code your clinician gave you, along with your email and a password.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold">Claim code</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              placeholder="Paste the code from your clinician"
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold">Full name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Jane Smith"
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.org"
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="At least 8 characters"
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-primary py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? "Please wait…" : "Set up my account"}
          </button>

          <p className="text-center text-sm text-muted">
            Already have an account? <Link href="/login" className="font-semibold text-primary">Sign in</Link>
          </p>
        </form>

        <p className="mt-4 text-center text-xs text-muted">
          Research and education use only — not a medical device.
        </p>
      </div>
    </div>
  );
}
