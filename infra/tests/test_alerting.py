"""Production's alert delivery (infra/alertmanager, docs/deploy.md): Alertmanager's config, the
message template and Prometheus's way to Alertmanager; then live checks with the real image (needs
Docker): the entrypoint, and one delivery to a fake Discord webhook and a fake SMTP server
(fake_receivers.py) on a throwaway network with no route out, so no message leaves the machine.
"""

import email
import json
import re
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[2]
INFRA = ROOT / "infra"
ALERTMANAGER = INFRA / "alertmanager"
CONFIG = ALERTMANAGER / "alertmanager.yml"
TEMPLATE = ALERTMANAGER / "filinglens.tmpl"
ENTRYPOINT = ALERTMANAGER / "entrypoint.sh"
FAKES = Path(__file__).with_name("fake_receivers.py")
# The entrypoint writes these from .env.prod; the config reads them.
WEBHOOK_FILE = "/tmp/discord-webhook-url"  # noqa: S108 - in the container
PASSWORD_FILE = "/tmp/smtp-password"  # noqa: S105, S108 - a path, not a password
RUNBOOKS = "https://github.com/kwnhyk04/filing-lens/"
# The live checks' values, under .env.prod's names; none may show in Alertmanager's log.
FAKE = {
    "ALERT_DISCORD_WEBHOOK_URL": "http://fakes:8080/api/webhooks/1/fake",
    "ALERT_SMTP_PASSWORD": "fake-password",
    "ALERT_EMAIL_FROM": "sender@example.com",
    "ALERT_EMAIL_TO": "inbox@example.com",
}
# Alertmanager as production runs it, with a tmpfs where production has its data volume.
HARDENED = (
    *("--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"),
    *("--tmpfs", "/tmp", "--tmpfs", "/alertmanager"),  # noqa: S108
)
# The fakes run on the Python the services build on (infra/Dockerfile), so no other image is pinned.
PYTHON = next(
    line.split()[1]
    for line in (INFRA / "Dockerfile").read_text(encoding="utf-8").splitlines()
    if line.startswith("FROM ")
)


def alert(name: str, summary: str, **labels: str) -> dict[str, Any]:
    """An alert as the rule `name` labels and annotates it."""
    runbook = f"{RUNBOOKS}blob/main/docs/monitoring.md#{name.lower()}"
    return {
        "labels": {"alertname": name, "severity": "critical", **labels},
        "annotations": {"summary": summary, "runbook_url": runbook},
    }


# The pair starts when it arrives, so its group waits for both; Alertmanager sends an alert that
# started over group_wait ago at once. The single alert started the day before.
ALERTS = [
    alert("WorkerNotConsuming", "Queue embed has had no consumer for 5 minutes.", queue="embed"),
    alert("WorkerNotConsuming", "Queue fetch has had no consumer for 5 minutes.", queue="fetch"),
    {
        **alert("AnswersFailing", "Two or more answers failed in the last 30 minutes."),
        "startsAt": "2026-10-24T14:03:00Z",
    },
]

type Run = Callable[..., subprocess.CompletedProcess[str]]
type Docker = Callable[..., str]
type WaitFor = Callable[..., bool]


def config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def channels() -> tuple[dict[str, Any], dict[str, Any]]:
    """The receiver's one Discord config and one email config."""
    (receiver,) = config()["receivers"]
    (discord,), (mail,) = receiver["discord_configs"], receiver["email_configs"]
    return discord, mail


def test_every_alert_goes_to_discord_and_email() -> None:
    found = config()
    assert found["route"]["receiver"] == "filinglens"
    assert "routes" not in found["route"]  # no alert takes another way
    (receiver,) = found["receivers"]
    assert set(receiver) == {"name", "discord_configs", "email_configs"}
    assert receiver["name"] == "filinglens"


def test_grouping_and_repeats_hold_back_a_flood() -> None:
    route = config()["route"]
    assert route["group_by"] == ["alertname"]  # one message per rule, its instances listed
    timing = (route["group_wait"], route["group_interval"], route["repeat_interval"])
    assert timing == ("30s", "10m", "12h")
    discord, mail = channels()
    assert discord["send_resolved"] is True  # Discord also says when an alert ends
    assert mail["send_resolved"] is False  # the inbox gets only what needs action


def test_secrets_and_addresses_stay_out_of_the_repo() -> None:
    smtp = config()["global"]
    discord, mail = channels()
    assert discord["webhook_url_file"] == WEBHOOK_FILE
    assert smtp["smtp_auth_password_file"] == PASSWORD_FILE
    # Placeholders, which the entrypoint replaces with .env.prod's addresses.
    assert (smtp["smtp_from"], smtp["smtp_auth_username"]) == ("ALERT_EMAIL_FROM",) * 2
    assert mail["to"] == "ALERT_EMAIL_TO"
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(ALERTMANAGER.iterdir()))
    assert not re.search(r"(?:webhook_url|auth_password|auth_secret)\s*:", text)  # none inline
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]", text)  # no address
    assert "discord.com/api/webhooks" not in text
    # The entrypoint writes exactly the files the config reads, then the config itself.
    written = re.findall(r"> (/tmp/\S+)", ENTRYPOINT.read_text(encoding="utf-8"))
    assert written == [WEBHOOK_FILE, PASSWORD_FILE, "/tmp/alertmanager.yml"]  # noqa: S108


def test_mail_and_webhooks_leave_through_the_egress_proxy() -> None:
    smtp = config()["global"]
    discord, _ = channels()
    assert discord["http_config"] == {"proxy_url": "http://egress-proxy:3130"}
    # Alertmanager sends no SMTP through a proxy: mail goes to the relay, with STARTTLS from
    # Alertmanager to Gmail, whose certificate is checked against Gmail's name.
    assert smtp["smtp_smarthost"] == "smtp-relay:2525"
    assert smtp["smtp_require_tls"] is True
    assert smtp["smtp_tls_config"] == {"server_name": "smtp.gmail.com"}


def test_messages_say_which_alert_and_since_when_and_link_nothing_private() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    # Alertmanager's own templates link to Alertmanager and Prometheus; ours, to the runbook alone.
    assert set(re.findall(r"\.(\w*url\w*)", template, flags=re.IGNORECASE)) == {"runbook_url"}
    assert ".StartsAt" in template
    discord, mail = channels()
    title, text = '{{ template "filinglens.title" . }}', '{{ template "filinglens.text" . }}'
    assert (discord["title"], discord["message"]) == (title, text)
    assert (mail["headers"], mail["text"]) == ({"Subject": title}, text)
    assert mail["html"] == ""  # no HTML part: Alertmanager's default one links to Alertmanager
    # amtool passes a templates path that matches no file, so check the mount's file is there.
    assert config()["templates"] == [f"/etc/alertmanager/{TEMPLATE.name}"]
    assert TEMPLATE.is_file()


def test_mounted_files_have_no_carriage_return() -> None:
    # Production mounts them from this checkout, where a CR breaks the script and the messages.
    # .gitattributes keeps them LF when git writes them, but not after an editor writes CRLF.
    for path in ALERTMANAGER.iterdir():
        assert b"\r" not in path.read_bytes(), path.name


def test_prometheus_sends_alerts_to_alertmanager_in_production_only() -> None:
    prometheus = yaml.safe_load((INFRA / "prometheus.yml").read_text(encoding="utf-8"))
    (alertmanagers,) = prometheus["alerting"]["alertmanagers"]
    assert alertmanagers == {"file_sd_configs": [{"files": ["prometheus-alertmanagers.yml"]}]}
    targets = INFRA / "prometheus-alertmanagers.yml"
    assert yaml.safe_load(targets.read_text(encoding="utf-8")) == [
        {"targets": ["alertmanager:9093"]}
    ]
    # Development mounts no such file, so its Prometheus sends nowhere and logs nothing.
    dev = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    assert targets.name not in dev


@pytest.fixture(scope="module")
def alertmanager(prod: dict[str, Any]) -> dict[str, Any]:
    """Production's Alertmanager service, from the compose model."""
    return prod["services"]["alertmanager"]


def launch(
    service: dict[str, Any], settings: dict[str, str], *command: str, conf: Path = CONFIG
) -> list[str]:
    """`docker run` arguments for the service as production runs it: its image and entrypoint,
    hardened, with infra/alertmanager mounted, `conf` over its alertmanager.yml, and `settings` as
    its environment. `command` replaces the service's own.

    Only the file is mounted from pytest's temporary directory: on Linux that directory is the
    runner's alone, and Alertmanager runs as nobody."""
    entrypoint, *script = service["entrypoint"]
    mounts = (
        f"type=bind,source={ALERTMANAGER},target=/etc/alertmanager,readonly",
        f"type=bind,source={conf},target=/etc/alertmanager/{CONFIG.name},readonly",
    )
    return [
        *HARDENED,
        *(arg for mount in mounts for arg in ("--mount", mount)),
        *(f"--env={name}={value}" for name, value in settings.items()),
        f"--entrypoint={entrypoint}",
        service["image"],
        *script,
        *(command or service["command"]),
    ]


@pytest.mark.integration
def test_compose_runs_alertmanager_with_its_settings_from_env_prod(
    alertmanager: dict[str, Any],
) -> None:
    assert re.fullmatch(r"prom/alertmanager:v[\d.]+@sha256:[0-9a-f]{64}", alertmanager["image"])
    assert alertmanager["entrypoint"] == ["/bin/sh", "/etc/alertmanager/entrypoint.sh"]
    assert alertmanager["command"] == [
        "/bin/alertmanager",
        "--config.file=/tmp/alertmanager.yml",
        "--storage.path=/alertmanager",
        "--cluster.listen-address=",
    ]
    # Empty when unset, so production's other commands run without them; the entrypoint stops.
    assert alertmanager["environment"] == {name: f"${{{name}:-}}" for name in FAKE}
    mounts = {volume["target"]: volume for volume in alertmanager["volumes"]}
    assert Path(mounts["/etc/alertmanager"]["source"]) == ALERTMANAGER
    assert mounts["/etc/alertmanager"]["read_only"] is True
    assert mounts["/alertmanager"]["source"] == "alertmanager-data"  # silences and what it sent


@pytest.mark.integration
def test_production_monitoring_publishes_only_grafana(prod: dict[str, Any]) -> None:
    services = prod["services"]
    monitoring = {"otel-collector", "jaeger", "prometheus", "grafana", "alertmanager"}
    on = {name for name, service in services.items() if "monitoring" in service["networks"]}
    assert on == monitoring
    assert prod["networks"]["monitoring"]["internal"] is True
    # The api sends its telemetry to the collector, and Prometheus reads RabbitMQ, on `data`.
    assert set(services["otel-collector"]["networks"]) == {"data", "monitoring"}
    assert set(services["prometheus"]["networks"]) == {"data", "monitoring"}
    assert set(services["jaeger"]["networks"]) == {"monitoring"}
    # Grafana shows Prometheus and Jaeger, on 127.0.0.1 and apart from dev's 3101.
    assert set(services["grafana"]["networks"]) == {"default", "monitoring"}
    (port,) = services["grafana"]["ports"]
    assert (port["host_ip"], port["published"], port["target"]) == ("127.0.0.1", "3111", 3000)
    assert not any(services[name].get("ports") for name in monitoring - {"grafana"})
    mounts = {volume["target"]: volume["source"] for volume in services["prometheus"]["volumes"]}
    target = "/etc/prometheus/prometheus-alertmanagers.yml"
    assert Path(mounts[target]) == INFRA / "prometheus-alertmanagers.yml"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ALERT_DISCORD_WEBHOOK_URL", ""),
        ("ALERT_SMTP_PASSWORD", ""),
        ("ALERT_EMAIL_FROM", ""),
        ("ALERT_EMAIL_TO", ""),
        ("ALERT_EMAIL_FROM", "sender@example.com/x"),
        ("ALERT_EMAIL_FROM", "a@example.com,b@example.com"),  # one sender
        ("ALERT_EMAIL_TO", "inbox@example.com x@example.com"),
        ("ALERT_EMAIL_TO", "inbox@example.com\nBcc: x@example.com"),
    ],
)
def test_the_entrypoint_stops_on_a_missing_or_unsafe_setting(
    name: str, value: str, alertmanager: dict[str, Any], run: Run
) -> None:
    done = run("run", "--rm", *launch(alertmanager, {**FAKE, name: value}, "true"))
    assert done.returncode == 1, done.stderr
    assert name in done.stderr
    assert not value or value not in done.stdout + done.stderr  # the name, never the value


@pytest.mark.integration
def test_the_entrypoint_hands_the_secrets_over_in_files(
    alertmanager: dict[str, Any], run: Run
) -> None:
    check = " && ".join(
        [
            f'stat -c "%a %s" {WEBHOOK_FILE} {PASSWORD_FILE}',
            "! env | grep ALERT_",  # the command's environment holds none of the four
            "! grep ALERT_ /tmp/alertmanager.yml",  # no placeholder left
            "amtool check-config /tmp/alertmanager.yml",
        ]
    )
    done = run("run", "--rm", *launch(alertmanager, FAKE, "/bin/sh", "-c", check))
    assert done.returncode == 0, done.stdout + done.stderr
    secrets = ("ALERT_DISCORD_WEBHOOK_URL", "ALERT_SMTP_PASSWORD")
    # Readable by Alertmanager alone, and exactly the value: no newline.
    assert done.stdout.splitlines()[:2] == [f"600 {len(FAKE[name])}" for name in secrets]
    assert "SUCCESS" in done.stdout


@pytest.mark.integration
def test_alerts_reach_discord_and_email_grouped_with_nothing_private(
    alertmanager: dict[str, Any], docker: Docker, run: Run, wait_for: WaitFor, tmp_path: Path
) -> None:
    # The fakes take no proxy and no TLS, and the first message leaves after a second. Each swap
    # changes one line of production's config; nothing else differs.
    swaps = {
        "        http_config: { proxy_url: http://egress-proxy:3130 }\n": "",
        "smtp_smarthost: smtp-relay:2525": "smtp_smarthost: fakes:2525",
        "smtp_require_tls: true": "smtp_require_tls: false",
        "group_wait: 30s": "group_wait: 1s",
    }
    text = CONFIG.read_text(encoding="utf-8")
    for old, new in swaps.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    conf = tmp_path / CONFIG.name
    conf.write_text(text, encoding="utf-8", newline="\n")
    network = f"filinglens-alert-test-{uuid.uuid4().hex[:8]}"
    fakes, manager = f"{network}-fakes", f"{network}-alertmanager"
    docker("network", "create", "--internal", network)
    try:
        locked = ("--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true")
        script = f"type=bind,source={FAKES},target=/fakes.py,readonly"
        where = ("--name", fakes, "--network", network, "--network-alias", "fakes", *locked)
        docker(
            "run",
            "--detach",
            *where,
            "--user",
            "65534",
            "--mount",
            script,
            PYTHON,
            "python",
            "-u",
            "/fakes.py",
        )
        where = ("--name", manager, "--network", network)
        docker("run", "--detach", *where, *launch(alertmanager, FAKE, conf=conf))
        ready = ("exec", manager, "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:9093/-/ready")
        assert wait_for(lambda: run(*ready).returncode == 0), run("logs", manager).stderr
        # One request, so the pair is in its group before the group's first message.
        post = ("--header", "Content-Type: application/json", "--post-data", json.dumps(ALERTS))
        api = "http://127.0.0.1:9093/api/v2/alerts"
        docker("exec", manager, "wget", "-q", "-O", "/dev/null", *post, api)

        def received() -> list[dict[str, Any]]:
            return [json.loads(line) for line in run("logs", fakes).stdout.splitlines()]

        assert wait_for(lambda: len(received()) >= 4, 60), run("logs", manager).stderr
        assert not wait_for(lambda: len(received()) > 4, 5)  # and nothing more
        messages, logs = received(), run("logs", manager)
    finally:
        run("rm", "--force", manager, fakes)
        run("network", "rm", network)

    grouped, single = (
        "FilingLens firing: WorkerNotConsuming (2)",
        "FilingLens firing: AnswersFailing",
    )
    posts = [message for message in messages if message["kind"] == "discord"]
    assert {post["path"] for post in posts} == {"/api/webhooks/1/fake"}
    texts = {
        embed["title"]: embed["description"] for embed in (p["body"]["embeds"][0] for p in posts)
    }
    assert sorted(texts) == sorted([grouped, single]) and len(posts) == 2  # one message per rule
    subjects = []
    for mail in (message for message in messages if message["kind"] == "email"):
        assert mail["auth"] == [FAKE["ALERT_EMAIL_FROM"], FAKE["ALERT_SMTP_PASSWORD"]]
        assert mail["mail_from"] == FAKE["ALERT_EMAIL_FROM"]
        assert mail["rcpt_to"] == [FAKE["ALERT_EMAIL_TO"]]
        message = email.message_from_string(mail["data"])
        assert (message["From"], message["To"]) == (
            FAKE["ALERT_EMAIL_FROM"],
            FAKE["ALERT_EMAIL_TO"],
        )
        parts = [part for part in message.walk() if not part.is_multipart()]
        assert [part.get_content_type() for part in parts] == ["text/plain"]  # no HTML part
        payload = parts[0].get_payload(decode=True)  # quoted-printable, decoded
        assert isinstance(payload, bytes)
        body = payload.decode().replace("\r\n", "\n")
        assert body.strip() == texts[message["Subject"]].strip()  # the same text as Discord's
        subjects.append(message["Subject"])
    assert sorted(subjects) == sorted([grouped, single])

    for found in ALERTS:
        title = grouped if found["labels"]["alertname"] == "WorkerNotConsuming" else single
        assert found["annotations"]["summary"] in texts[title]
        assert found["annotations"]["runbook_url"] in texts[title]
    assert len(re.findall(r"Firing since \d{4}-\d\d-\d\d \d\d:\d\d UTC", texts[grouped])) == 2
    assert "Firing since 2026-10-24 14:03 UTC" in texts[single]
    for text in texts.values():
        assert all(url.startswith(RUNBOOKS) for url in re.findall(r"https?://\S+", text))
    assert not any(value in logs.stdout + logs.stderr for value in FAKE.values())
