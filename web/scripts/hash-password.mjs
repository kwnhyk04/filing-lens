// `npm run hash-password`: asks for the sign-in password twice without echo, then prints the
// single-quoted LOGIN_PASSWORD_HASH line to paste into the repo's .env (single quotes keep the $).
import { hashPassword } from "../lib/password.ts";

const MIN_LENGTH = 12;

function fail(message, code = 1) {
  console.error(message);
  process.exit(code);
}

/** Reads one line from the terminal in raw mode, so nothing is echoed. */
function askHidden(prompt) {
  const { stdin, stderr } = process;
  stderr.write(prompt);
  stdin.setRawMode(true);
  stdin.setEncoding("utf8");
  stdin.resume();
  return new Promise((resolve) => {
    let value = "";
    const onData = (chunk) => {
      for (const char of chunk) {
        if (char === "\u0003") fail("\nCancelled.", 130);
        if (char === "\r" || char === "\n") {
          stdin.off("data", onData);
          stdin.setRawMode(false);
          stdin.pause();
          stderr.write("\n");
          resolve(value);
          return;
        }
        value = char === "\u007f" || char === "\b" ? value.slice(0, -1) : value + char;
      }
    };
    stdin.on("data", onData);
  });
}

if (!process.stdin.isTTY) fail("hash-password needs a terminal: run it in your own PowerShell window.");
const password = await askHidden("Sign-in password: ");
if ((await askHidden("Again: ")) !== password) fail("The two entries differ; nothing was printed.");
if ([...password].length < MIN_LENGTH) fail(`Use at least ${MIN_LENGTH} characters.`);
console.log(`LOGIN_PASSWORD_HASH='${await hashPassword(password)}'`);
