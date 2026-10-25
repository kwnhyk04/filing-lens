"""A fake Discord webhook (HTTP on 8080) and a fake SMTP server (on 2525) for test_alerting.py,
which runs this in a container on its throwaway network. Each message received is printed as one
JSON line. Stdlib only and no TLS: the SMTP server offers AUTH LOGIN alone, which Alertmanager
sends without TLS.
"""

import base64
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOCK = threading.Lock()


def emit(**record: Any) -> None:
    with LOCK:  # one whole line per message, whichever thread received it
        print(json.dumps(record), flush=True)


class Webhook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # http.server's name
        body = self.rfile.read(int(self.headers["Content-Length"]))
        emit(kind="discord", path=self.path, body=json.loads(body))
        self.send_response(204)
        self.end_headers()


class Smtp(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write(f"{line}\r\n".encode())

    def read(self) -> str:
        line = self.rfile.readline()
        if not line:
            raise EOFError
        return line.decode().rstrip("\r\n")

    def handle(self) -> None:
        record: dict[str, Any] = {"kind": "email", "rcpt_to": []}
        self.reply("220 fake ESMTP")
        try:
            while True:
                command = self.read()
                verb = command.split(" ", 1)[0].upper()
                if verb == "EHLO":
                    self.reply("250-fake")
                    self.reply("250 AUTH LOGIN")
                elif verb == "AUTH":
                    self.reply("334 " + base64.b64encode(b"Username:").decode())
                    user = base64.b64decode(self.read()).decode()
                    self.reply("334 " + base64.b64encode(b"Password:").decode())
                    record["auth"] = [user, base64.b64decode(self.read()).decode()]
                    self.reply("235 2.7.0 Authentication successful")
                elif verb == "MAIL":
                    record["mail_from"] = command.split(":", 1)[1].strip("<> ")
                    self.reply("250 OK")
                elif verb == "RCPT":
                    record["rcpt_to"].append(command.split(":", 1)[1].strip("<> "))
                    self.reply("250 OK")
                elif verb == "DATA":
                    self.reply("354 End data with <CR><LF>.<CR><LF>")
                    lines: list[str] = []
                    while (line := self.read()) != ".":
                        lines.append(line[1:] if line.startswith(".") else line)  # dot-stuffing
                    record["data"] = "\r\n".join(lines)
                    self.reply("250 OK")
                elif verb == "QUIT":
                    self.reply("221 Bye")
                    break
                else:
                    self.reply("250 OK")
        except EOFError:
            pass
        if "data" in record:
            emit(**record)


def main() -> None:
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    smtp = socketserver.ThreadingTCPServer(("0.0.0.0", 2525), Smtp)  # noqa: S104 - its container's
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Webhook).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
