// `npm run session-secret`: appends SESSION_SECRET (32 random bytes, hex) to the repo's .env.
// It prints nothing, and refuses when the line exists: to rotate, delete it and run this again.
import { randomBytes } from "node:crypto";
import { appendFileSync, readFileSync } from "node:fs";

function read(path) {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return "";
    throw error;
  }
}

const path = process.argv[2] ?? new URL("../../.env", import.meta.url);
const text = read(path);
if (/^\s*SESSION_SECRET\s*=/m.test(text)) {
  console.error("SESSION_SECRET is already in .env. To rotate it, delete that line and run this again.");
  process.exit(1);
}
const newline = text && !text.endsWith("\n") ? "\n" : "";
appendFileSync(path, `${newline}SESSION_SECRET=${randomBytes(32).toString("hex")}\n`);
