"use client";
// The landing page's header, after the 21st.dev hero the user picked for it (hero4's header only), in
// FilingLens's colours: the mark and the name, the page's sections, then the theme, Sign in and the demo.
// It sticks to the top, see-through over the hero until the page scrolls; below 64rem the sections, the
// theme and Sign in fold into a menu.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { Theme } from "../lib/theme.ts";
import { ThemeToggle } from "./theme-toggle.tsx";

const REPO = "https://github.com/kwnhyk04/filing-lens";
const SECTIONS: [href: string, label: string][] = [
  ["#how", "How it works"],
  ["#results", "Results"],
  ["#architecture", "Architecture"],
  [REPO, "GitHub"],
];

export function LandingHeader({ theme }: { theme: Theme }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);

  const shut = () => setOpen(false);
  return (
    <header className="landing-head" data-scrolled={scrolled} data-open={open}>
      <Link href="/" className="brand">
        FilingLens
      </Link>
      <button
        ref={toggle}
        type="button"
        className="menu-toggle"
        aria-expanded={open}
        aria-controls="landing-menu"
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d={open ? "M18 6 6 18M6 6l12 12" : "M4 7h16M4 12h16M4 17h16"} />
        </svg>
        <span className="visually-hidden">Menu</span>
      </button>
      <div id="landing-menu" className="landing-menu">
        <nav aria-label="Main">
          {SECTIONS.map(([href, label]) => (
            <a key={href} href={href} onClick={shut}>
              {label}
            </a>
          ))}
        </nav>
        <div className="landing-actions">
          <ThemeToggle theme={theme} />
          <Link href="/login" className="sign-in" prefetch={false} onClick={shut}>
            Sign in
          </Link>
        </div>
      </div>
      <Link href="/demo" className="button">
        Open the demo
      </Link>
    </header>
  );
}
