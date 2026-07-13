"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const USER_STORAGE_KEY = "formaos_homeowner";

type StoredHomeowner = {
  id: string;
  name: string;
  email: string;
};

function userIdFromEmail(email: string) {
  return `homeowner-${email.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

export function LoginClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/workspace";
  const [name, setName] = useState("Anaya");
  const [email, setEmail] = useState("anaya@example.com");
  const [currentUser, setCurrentUser] = useState<StoredHomeowner | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(USER_STORAGE_KEY);
    if (!stored) return;
    try {
      setCurrentUser(JSON.parse(stored) as StoredHomeowner);
    } catch {
      window.localStorage.removeItem(USER_STORAGE_KEY);
    }
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    const cleanName = name.trim() || cleanEmail.split("@")[0] || "Homeowner";
    const user: StoredHomeowner = {
      id: userIdFromEmail(cleanEmail),
      name: cleanName,
      email: cleanEmail,
    };
    window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    window.dispatchEvent(new CustomEvent("formaos-user-change", { detail: user }));
    router.push(next.startsWith("/") ? next : "/workspace");
  }

  function signOut() {
    window.localStorage.removeItem(USER_STORAGE_KEY);
    window.dispatchEvent(new CustomEvent("formaos-user-change"));
    setCurrentUser(null);
  }

  return (
    <main className="page-shell login-page">
      <section className="login-shell">
        <div className="login-copy">
          <span className="eyebrow">Homeowner account</span>
          <h1>Sign in before you design so every room version is saved to you.</h1>
          <p>
            This prototype uses a local homeowner profile to attach generated designs,
            revisions, exports, and saved concepts to one person.
          </p>
          <div className="login-proof-grid" aria-label="What sign-in enables">
            <article>
              <strong>Saved designs</strong>
              <span>Only your generated versions show in the workspace.</span>
            </article>
            <article>
              <strong>Revision memory</strong>
              <span>Reopen a saved design and revise it without losing the original brief.</span>
            </article>
            <article>
              <strong>Export handoff</strong>
              <span>Keep the room brief, selected products, checks, and image prompt together.</span>
            </article>
          </div>
        </div>

        <form className="login-card" onSubmit={handleSubmit}>
          <div>
            <span className="eyebrow">Prototype login</span>
            <h2>Continue as homeowner</h2>
          </div>
          <label>
            Name
            <input className="text-input" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Email
            <input
              className="text-input"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit">
            Save and enter workspace
          </button>
          {currentUser ? (
            <button className="secondary-button" type="button" onClick={signOut}>
              Sign out {currentUser.name}
            </button>
          ) : null}
          <p>
            For production, replace this with hosted identity or OAuth. The current goal is
            correct save ownership while the app workflow is being built.
          </p>
          <Link className="secondary-button" href="/">
            Back to landing
          </Link>
        </form>
      </section>
    </main>
  );
}
