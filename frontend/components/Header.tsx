"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const NAV_ITEMS = [
  { href: "/", label: "New Script" },
  { href: "/history", label: "History" },
  { href: "/trends", label: "Trends" },
  { href: "/plans", label: "Plans" },
  { href: "/billing", label: "Billing" },
  { href: "/settings", label: "Settings" },
];

export function Header() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("ytg_theme");
    const isDark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    window.localStorage.setItem("ytg_theme", next ? "dark" : "light");
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          YouTube Script Generator
        </Link>
        <nav className="ml-6 flex flex-1 gap-4 overflow-x-auto text-sm">
          {NAV_ITEMS.map((item) => (
            <Link key={item.href} href={item.href} className="whitespace-nowrap text-muted-foreground hover:text-foreground">
              {item.label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          onClick={toggleTheme}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground"
          aria-label="Toggle dark mode"
        >
          {dark ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
