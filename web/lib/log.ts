// One JSON line per event; callers pass no question, key or cookie.
type Field = string | number | boolean | undefined;

export function log(event: string, fields: Record<string, Field> = {}, level = "info"): void {
  const line = { ts: new Date().toISOString(), level, service: "filinglens-web", event, ...fields };
  (level === "error" ? console.error : console.log)(JSON.stringify(line));
}
