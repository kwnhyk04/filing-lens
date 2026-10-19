// Checks the settings once when the server starts; only the Node.js runtime loads the check.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" && process.env.NEXT_PHASE !== "phase-production-build") {
    await import("./lib/startup.ts");
  }
}
