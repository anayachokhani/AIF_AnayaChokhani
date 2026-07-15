"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_FORMAOS_API_BASE ?? "http://localhost:8000";

type AuthMode = "login" | "signup";

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function authError(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return "We could not sign you in. Please try again.";
  const detail = (payload as { detail?: { message?: string } }).detail;
  return detail?.message ?? "We could not sign you in. Please try again.";
}

export function LoginClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/workspace";
  const [mode, setMode] = useState<AuthMode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(apiUrl("/api/auth/me"), { credentials: "include" })
      .then((response) => {
        if (response.ok) router.replace(next.startsWith("/") ? next : "/workspace");
      })
      .finally(() => setCheckingSession(false));
  }, [next, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl(mode === "signup" ? "/api/auth/signup" : "/api/auth/login"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "signup" ? { name: name.trim(), email: email.trim(), password } : { email: email.trim(), password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(authError(payload));
      router.replace(next.startsWith("/") ? next : "/workspace");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not sign you in. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <Link className="auth-brand" href="/" aria-label="YourSpace home">
        <img src="/yourspace-logo.png" alt="" />
        <strong>YourSpace</strong>
      </Link>

      <section className="auth-shell">
        <div className="auth-copy">
          <span className="eyebrow">Your private design studio</span>
          <h1>Every room, revision, and recommendation stays with your account.</h1>
          <p>Sign in once to return to previous projects, continue each project chat, and keep furniture decisions separate for every room.</p>
          <div className="auth-proof-list" aria-label="Account benefits">
            <div><span>01</span><p><strong>One project per room</strong>Your photos, brief, generated images, and product plan stay together.</p></div>
            <div><span>02</span><p><strong>Saved design history</strong>Reopen a project and revise it without starting again.</p></div>
            <div><span>03</span><p><strong>Private account session</strong>Your identity is held by the server, not editable browser storage.</p></div>
          </div>
        </div>

        <div className="auth-card">
          <div className="auth-mode-switch" aria-label="Account action">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
            <button type="button" className={mode === "signup" ? "active" : ""} onClick={() => { setMode("signup"); setError(""); }}>Create account</button>
          </div>
          <div className="auth-card-heading">
            <h2>{mode === "login" ? "Welcome back" : "Create your homeowner account"}</h2>
            <p>{mode === "login" ? "Continue where you left off." : "Start a private project library for your home."}</p>
          </div>
          <form onSubmit={handleSubmit}>
            {mode === "signup" ? (
              <label>Full name<input autoComplete="name" required minLength={2} value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" /></label>
            ) : null}
            <label>Email address<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
            <label>
              Password
              <span className="auth-password-field">
                <input autoComplete={mode === "login" ? "current-password" : "new-password"} type={showPassword ? "text" : "password"} required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </span>
            </label>
            {error ? <p className="auth-error" role="alert">{error}</p> : null}
            <button className="ys-solid-button auth-submit" type="submit" disabled={loading || checkingSession}>
              {loading ? "Please wait..." : checkingSession ? "Checking account..." : mode === "login" ? "Sign in to YourSpace" : "Create account"}
            </button>
          </form>
          <p className="auth-privacy">Your account session is stored in a secure, HttpOnly cookie. Passwords are salted and hashed before storage.</p>
        </div>
      </section>
    </main>
  );
}
