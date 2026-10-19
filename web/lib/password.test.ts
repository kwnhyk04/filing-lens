// Sign-in password hashing under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { hashPassword, parsePhc, verifyPassword } from "./password.ts";

// The argon2 reference implementation's (RFC 9106's code) output for "password" and "somesalt".
const REFERENCE = "$argon2id$v=19$m=65536,t=2,p=1$c29tZXNhbHQ$CTFhFdXPJO1aFaMaO6Mm5c8y7cJHAph8ArZWb2GRPPc";

test("verifies the argon2 reference implementation's hash, and nothing else", async () => {
  assert.equal(await verifyPassword("password", parsePhc(REFERENCE)), true);
  assert.equal(await verifyPassword("Password", parsePhc(REFERENCE)), false);
  assert.equal(await verifyPassword("", parsePhc(REFERENCE)), false);
});

test("a fresh hash round-trips, with RFC 9106's second recommended parameters", async () => {
  const phc = await hashPassword("correct horse battery");
  assert.match(phc, /^\$argon2id\$v=19\$m=65536,t=3,p=4\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$/);
  assert.equal(await verifyPassword("correct horse battery", parsePhc(phc)), true);
  assert.equal(await verifyPassword("correct horse batterz", parsePhc(phc)), false);
  assert.notEqual(await hashPassword("correct horse battery"), phc, "each hash has its own salt");
});

const MALFORMED: [string, string][] = [
  ["empty", ""],
  ["argon2i", REFERENCE.replace("argon2id", "argon2i")],
  ["another version", REFERENCE.replace("v=19", "v=16")],
  ["memory below 19 MiB", REFERENCE.replace("m=65536", "m=1024")],
  ["memory above 1 GiB", REFERENCE.replace("m=65536", "m=2097152")],
  ["one pass", REFERENCE.replace("t=2", "t=1")],
  ["too many passes", REFERENCE.replace("t=2", "t=11")],
  ["no lanes", REFERENCE.replace("p=1", "p=0")],
  ["a salt under 8 bytes", REFERENCE.replace("c29tZXNhbHQ", "c29tZQ")],
  ["a hash under 16 bytes", REFERENCE.replace(/\$[^$]+$/, "$c29tZXNhbHQ")],
  ["a missing field", REFERENCE.replace(/\$[^$]+$/, "")],
  ["base64 padding", `${REFERENCE}=`],
  ["surrounding quotes", `'${REFERENCE}'`],
];

for (const [name, phc] of MALFORMED) {
  test(`refuses a PHC string with ${name}`, () => {
    assert.throws(() => parsePhc(phc), /argon2id/);
  });
}

test("the parse error never echoes the string", () => {
  const phc = REFERENCE.replace("v=19", "v=16");
  assert.throws(() => parsePhc(phc), (error: Error) => !error.message.includes("CTFhFd"));
});
