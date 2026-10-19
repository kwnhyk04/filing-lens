// Imported once when the server starts (instrumentation.ts): a bad setting stops it, naming the variable.
import { log } from "./log.ts";
import { loadSettings } from "./settings.ts";

try {
  loadSettings(process.env);
} catch (error) {
  log("invalid_configuration", { detail: (error as Error).message }, "error");
  process.exit(1);
}
