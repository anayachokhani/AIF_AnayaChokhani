"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navItems } from "../data";

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <Link className="brand-lockup" href="/" aria-label="FormaOS overview">
        <span className="brand-mark">F</span>
        <span>
          <strong>FormaOS</strong>
          <small>Buildable interior plans</small>
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
    </header>
  );
}
