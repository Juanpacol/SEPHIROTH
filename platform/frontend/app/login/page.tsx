"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { storeAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
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
      router.push("/dashboard");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      if (message.includes("409")) setError("That email is already registered.");
      else if (message.includes("401")) setError("Invalid email or password.");
      else if (message.includes("422")) setError("Check your input (password ≥ 8 chars).");
      else setError("Could not reach the server. Is the backend running?");
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
            <h1 className="font-extrabold">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="text-sm text-muted">
              {mode === "login"
                ? "Sign in to access your consultations"
                : "Register as a clinician to get started"}
            </p>
          </div>

          {mode === "register" && (
            <div>
              <label className="mb-1 block text-sm font-semibold">Full name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="Dr. Jane Smith"
                className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-semibold">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@hospital.org"
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
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>

          <p className="text-center text-sm text-muted">
            {mode === "login" ? "No account yet?" : "Already registered?"}{" "}
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="font-semibold text-primary"
            >
              {mode === "login" ? "Register" : "Sign in"}
            </button>
          </p>
        </form>

        <p className="mt-4 text-center text-xs text-muted">
          Research and education use only — not a medical device.
        </p>
      </div>
    </div>
  );
}
