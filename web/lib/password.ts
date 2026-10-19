// Sign-in passwords: argon2id from node:crypto, stored as a PHC string with bounded parameters.
import { argon2, randomBytes, timingSafeEqual } from "node:crypto";

export interface Phc {
  memory: number; // KiB
  passes: number;
  parallelism: number;
  salt: Buffer;
  hash: Buffer;
}

// RFC 9106's second recommended option: 64 MiB, 3 passes, 4 lanes, a 16-byte salt, a 32-byte tag.
const DEFAULTS = { memory: 65536, passes: 3, parallelism: 4 };
const PHC = /^\$argon2id\$v=19\$m=(\d{1,8}),t=(\d{1,2}),p=(\d{1,2})\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)$/;
const INVALID = "not an argon2id hash from `npm run hash-password`";

function within(value: number, low: number, high: number): boolean {
  return value >= low && value <= high;
}

/** Parses `$argon2id$v=19$m=..,t=..,p=..$salt$hash`; the error never echoes the string. */
export function parsePhc(phc: string): Phc {
  const match = PHC.exec(phc);
  if (!match) throw new Error(INVALID);
  const [memory, passes, parallelism] = match.slice(1, 4).map(Number);
  const salt = Buffer.from(match[4], "base64");
  const hash = Buffer.from(match[5], "base64");
  // OWASP's 19 MiB floor up to 1 GiB, 2 to 10 passes, 1 to 16 lanes, RFC 9106's 8-byte salt floor.
  const sane =
    within(memory, 19456, 1048576) &&
    within(passes, 2, 10) &&
    within(parallelism, 1, 16) &&
    salt.length >= 8 &&
    within(hash.length, 16, 64);
  if (!sane) throw new Error(INVALID);
  return { memory, passes, parallelism, salt, hash };
}

function derive(password: string, phc: Omit<Phc, "hash">, tagLength: number): Promise<Buffer> {
  const { memory, passes, parallelism, salt } = phc;
  return new Promise((resolve, reject) =>
    argon2(
      "argon2id",
      { message: password, nonce: salt, memory, passes, parallelism, tagLength },
      (error, tag) => (error ? reject(error) : resolve(tag)),
    ),
  );
}

export async function verifyPassword(password: string, phc: Phc): Promise<boolean> {
  return timingSafeEqual(await derive(password, phc, phc.hash.length), phc.hash);
}

const b64 = (bytes: Buffer) => bytes.toString("base64").replace(/=+$/, "");

/** A new PHC string for `LOGIN_PASSWORD_HASH`. */
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const hash = await derive(password, { ...DEFAULTS, salt }, 32);
  const { memory, passes, parallelism } = DEFAULTS;
  return `$argon2id$v=19$m=${memory},t=${passes},p=${parallelism}$${b64(salt)}$${b64(hash)}`;
}
