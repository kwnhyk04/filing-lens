"use client";
// The theme switch: System, Light or Dark, as three radios with icons. The choice goes into the fl-theme
// cookie, which the root layout reads for every page after this one, and onto <html> at once.
import { type ReactNode, useId, useState } from "react";

import { type Theme, themeCookie } from "../lib/theme.ts";

// Lucide's monitor, sun and moon (ISC licence, docs/third-party.md).
const CHOICES: { theme: Theme; label: string; icon: ReactNode }[] = [
  {
    theme: "system",
    label: "System",
    icon: (
      <>
        <rect width="20" height="14" x="2" y="3" rx="2" />
        <path d="M8 21h8M12 17v4" />
      </>
    ),
  },
  {
    theme: "light",
    label: "Light",
    icon: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
      </>
    ),
  },
  { theme: "dark", label: "Dark", icon: <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /> },
];

export function ThemeToggle({ theme }: { theme: Theme }) {
  const [current, setCurrent] = useState(theme);
  const name = useId();

  function pick(next: Theme) {
    setCurrent(next);
    document.cookie = themeCookie(next, location.protocol === "https:");
    const root = document.documentElement;
    if (next === "system") delete root.dataset.theme;
    else root.dataset.theme = next;
  }

  return (
    <fieldset className="theme-toggle">
      <legend className="visually-hidden">Theme</legend>
      {CHOICES.map((choice) => (
        <label key={choice.theme} title={choice.label}>
          <input
            type="radio"
            name={name}
            value={choice.theme}
            checked={current === choice.theme}
            onChange={() => pick(choice.theme)}
          />
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            {choice.icon}
          </svg>
          <span className="visually-hidden">{choice.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
