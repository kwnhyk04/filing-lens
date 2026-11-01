// The visitor's theme: Light, Dark or the system's. A cookie keeps it and the root layout reads it, so the
// server renders every page in it and nothing flashes. No cookie means the system's.
export const THEME_COOKIE = "fl-theme";
export type Theme = "system" | "light" | "dark";
const YEAR_S = 365 * 24 * 60 * 60;

export const themeOf = (value: string | undefined): Theme => (value === "light" || value === "dark" ? value : "system");

/** The `document.cookie` assignment for `theme`: kept a year on the whole site; System deletes it. */
export function themeCookie(theme: Theme, secure: boolean): string {
  const value = theme === "system" ? "=; Max-Age=0" : `=${theme}; Max-Age=${YEAR_S}`;
  return `${THEME_COOKIE}${value}; Path=/; SameSite=Lax${secure ? "; Secure" : ""}`;
}

/** How the page looks: the theme picked, or the system's when that is System. */
export const appearance = (theme: Theme, systemDark: boolean): "light" | "dark" =>
  theme === "system" ? (systemDark ? "dark" : "light") : theme;
