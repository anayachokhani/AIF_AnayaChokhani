"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { navItems } from "../data";

const USER_STORAGE_KEY = "formaos_homeowner";

type StoredHomeowner = {
  id: string;
  name: string;
  email: string;
};

export function SiteNav() {
  const pathname = usePathname();
  const [homeowner, setHomeowner] = useState<StoredHomeowner | null>(null);

  useEffect(() => {
    function readUser() {
      const stored = window.localStorage.getItem(USER_STORAGE_KEY);
      if (!stored) {
        setHomeowner(null);
        return;
      }
      try {
        setHomeowner(JSON.parse(stored) as StoredHomeowner);
      } catch {
        window.localStorage.removeItem(USER_STORAGE_KEY);
        setHomeowner(null);
      }
    }

    readUser();
    window.addEventListener("storage", readUser);
    window.addEventListener("formaos-user-change", readUser);
    return () => {
      window.removeEventListener("storage", readUser);
      window.removeEventListener("formaos-user-change", readUser);
    };
  }, []);

  function signOut() {
    window.localStorage.removeItem(USER_STORAGE_KEY);
    window.dispatchEvent(new CustomEvent("formaos-user-change"));
    setHomeowner(null);
  }

  return (
    <header className="site-header">
      <Link className="brand-lockup" href="/" aria-label="YourSpace home">
        <img className="ys-logo-image" src="/yourspace-logo.png" alt="" />
        <span>
          <strong>YourSpace</strong>
          <small>AI home design</small>
        </span>
      </Link>
      <nav className="nav-bar" aria-label="Primary navigation">
        {navItems.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              className={active ? "nav-link active" : "nav-link"}
              href={item.href}
              aria-current={active ? "page" : undefined}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="nav-account" aria-label="Account">
        {homeowner ? (
          <>
            <span>{homeowner.name}</span>
            <button type="button" onClick={signOut}>
              Sign out
            </button>
          </>
        ) : (
          <Link href={`/login?next=${encodeURIComponent(pathname || "/workspace")}`}>Sign in</Link>
        )}
      </div>
    </header>
  );
}
