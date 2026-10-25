"""Production's egress proxy (infra/squid, docs/deploy.md): its allowlists, how compose wires its
four clients, and live checks that it and the mail relay refuse what they must (needs Docker).

The live checks run the proxy on a throwaway internal network with no route out, and its
/etc/hosts maps every name the probes ask for, so no request leaves the machine: squid answers an
allowed request with 503 when it finds no route, and refuses the rest with 403.
"""

import ipaddress
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from filinglens_llm.providers import BASE_URLS

ROOT = Path(__file__).parents[2]
SQUID = ROOT / "infra" / "squid"
SQUID_CONF = SQUID / "squid.conf"
ALERTMANAGER_CONFIG = ROOT / "infra" / "alertmanager" / "alertmanager.yml"
# What production calls (docs/deploy.md, Models): Claude, then Gemini, then NVIDIA; Groq routes.
API_HOSTS = {
    "api.anthropic.com",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "integrate.api.nvidia.com",
}
# Tailscale's control plane and Funnel's certificate; the relays match DERP.
TAILSCALE_HOSTS = {"acme-v02.api.letsencrypt.org", "controlplane.tailscale.com"}
DERP = "^derp[0-9]+[a-z]*[.]tailscale[.]com$"
# Alert delivery (docs/deploy.md): Discord's webhooks, and Gmail's SMTP through the mail relay.
DISCORD, GMAIL = "discord.com", "smtp.gmail.com"
NO_PROXY = "postgres,redis,rabbitmq,otel-collector,localhost,127.0.0.1,::1"
# Each client's squid port, and its network and fixed address in production; squid.conf ties the
# port to the address. Alertmanager and its relay sit on `alerting`, out of the api's reach.
CLIENTS = {
    "api": (3128, "outbound", "10.231.232.2"),
    "tailscale": (3129, "outbound", "10.231.232.3"),
    "alertmanager": (3130, "alerting", "10.231.232.18"),
    "smtp_relay": (3131, "alerting", "10.231.232.19"),
}

IMAGE = "filinglens-squid:test"
TEST_NET = ("10.231.233.0/28", "10.231.233.8/29")  # subnet and dynamic range; production's is .232
TEST_ADDRESSES = {
    "api": "10.231.233.2",
    "tailscale": "10.231.233.3",
    "alertmanager": "10.231.233.4",
    "smtp_relay": "10.231.233.5",
}
PROXY, OTHER = "10.231.233.7", "10.231.233.9"
UNREACHABLE = "203.0.113.10"  # a public address (TEST-NET-3) with no route from the test network
ALLOWED, REFUSED = "503", "403"
# The proxy as production runs it (test_the_proxy_is_pinned_and_locked_down).
TMPFS = ("/tmp", "/var/spool/squid", "/var/log/squid", "/run")  # noqa: S108 - in the container
HARDENED = (
    *("--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"),
    *(f"--tmpfs={path}" for path in TMPFS),
)
# Every name the probes ask for, as the proxy's /etc/hosts maps it, so squid sends no DNS query.
HOSTS = {
    **dict.fromkeys(
        [
            *API_HOSTS,
            *TAILSCALE_HOSTS,
            "derp1f.tailscale.com",
            "derp12.tailscale.com",
            "derp1.tailscale.com.example.org",
            "log.tailscale.com",
            "example.com",
            DISCORD,
            "discordapp.com",
            "canary.discord.com",
            "discord.com.example.org",
            GMAIL,
            "gmail.com",
            "smtp.gmail.com.example.org",
        ],
        UNREACHABLE,
    ),
    # A relay's name that resolves to a private address, and Docker Desktop's way to the PC.
    "derp99.tailscale.com": "host-gateway",
    "host.docker.internal": "host-gateway",
}
# Sends each "<port> <request line>" to the proxy and prints it with squid's status code, or tries
# "direct <host> <port>" without the proxy and prints open or closed.
PROBE = r"""
set -f
for spec in "$@"; do
  set -- $spec
  if [ "$1" = direct ]; then
    timeout 5 bash -c 'exec 3<>"/dev/tcp/$0/$1"' "$2" "$3" 2>/dev/null && code=open || code=closed
  else
    code=$(timeout 10 bash -c 'exec 3<>"/dev/tcp/$0/$1" || exit
      printf "%s HTTP/1.1\r\nHost: x\r\n\r\n" "$2" >&3
      read -r _ code _ <&3 && echo "$code"' "$PROXY" "$1" "${spec#* }" 2>/dev/null)
  fi
  echo "$spec|${code:-none}"
done
"""
# Opens a connection to the mail relay at $0 and waits until the relay closes it.
RELAY_CLIENT = 'exec 3<>"/dev/tcp/$0/2525" && timeout 5 cat <&3 > /dev/null; exit 0'

type Probe = Callable[..., dict[str, str]]
type Run = Callable[..., subprocess.CompletedProcess[str]]
type Docker = Callable[..., str]
type WaitFor = Callable[..., bool]


def directives(name: str) -> list[list[str]]:
    """The words after `name` on each line of squid.conf that starts with it."""
    lines = (line.split() for line in SQUID_CONF.read_text(encoding="utf-8").splitlines())
    return [words[1:] for words in lines if words and words[0] == name]


def acls() -> dict[str, list[list[str]]]:
    """Each ACL's lines by name: its type and values, one list per line."""
    found: dict[str, list[list[str]]] = {}
    for name, *rest in directives("acl"):
        found.setdefault(name, []).append(rest)
    return found


def service(client: str) -> str:
    """A client's compose service: squid's names take `_`, compose's `-`."""
    return client.replace("_", "-")


def test_each_client_has_its_own_port_and_address() -> None:
    ports = [[str(port), f"name={client}"] for client, (port, _, _) in CLIENTS.items()]
    assert directives("http_port") == ports
    found = acls()
    for client, (_, _, address) in CLIENTS.items():
        assert found[f"from_{client}"] == [["myportname", client]]
        assert found[f"{client}_ip"] == [["src", address]]


def test_refusals_come_before_the_allowlists() -> None:
    assert directives("http_access") == [
        ["deny", "!CONNECT"],
        # SMTP's port only on the mail relay's proxy port, HTTPS's on every other.
        ["deny", "from_smtp_relay", "!smtp_port"],
        ["deny", "!from_smtp_relay", "!https_port"],
        ["deny", "non_public"],
        ["allow", "from_api", "api_ip", "api_hosts"],
        ["allow", "from_tailscale", "tailscale_ip", "tailscale_hosts"],
        ["allow", "from_tailscale", "tailscale_ip", "tailscale_derp"],
        ["allow", "from_alertmanager", "alertmanager_ip", "alertmanager_hosts"],
        ["allow", "from_smtp_relay", "smtp_relay_ip", "smtp_relay_hosts"],
        ["deny", "all"],
    ]
    found = acls()
    assert found["CONNECT"] == [["method", "CONNECT"]]
    assert found["https_port"] == [["port", "443"]]
    assert found["smtp_port"] == [["port", "587"]]
    assert {line[0] for line in found["non_public"]} == {"dst"}
    ranges = {value for line in found["non_public"] for value in line[1:]}
    private = ["10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12"]
    assert {*private, "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10"} <= ranges


def test_the_allowlists_hold_only_what_production_calls() -> None:
    found = acls()
    assert found["api_hosts"] == [["dstdomain", "-n", *sorted(API_HOSTS)]]
    assert found["tailscale_hosts"] == [["dstdomain", "-n", *sorted(TAILSCALE_HOSTS)]]
    assert found["tailscale_derp"] == [["dstdom_regex", "-n", DERP]]
    assert found["alertmanager_hosts"] == [["dstdomain", "-n", DISCORD]]
    assert found["smtp_relay_hosts"] == [["dstdomain", "-n", GMAIL]]
    # A provider URL that moves in code must move here too.
    assert {urlsplit(BASE_URLS[name]).hostname for name in ("groq", "nvidia")} <= API_HOSTS


@pytest.mark.integration
def test_only_the_proxy_has_a_route_out(prod: dict[str, Any]) -> None:
    services, networks = prod["services"], prod["networks"]
    on = {
        network: {name for name, service in services.items() if network in service["networks"]}
        for network in networks
    }
    routed = {name for name, network in networks.items() if not network.get("internal")}
    assert routed == {"default", "egress"}
    assert on["egress"] == {"egress-proxy"}
    # Grafana for its one 127.0.0.1 port, ingest for SEC (todo.md), toxiproxy in the test profile.
    assert on["default"] == {"grafana", "ingest", "toxiproxy"}
    assert on["outbound"] == {"api", "tailscale", "egress-proxy"}
    # Neither the api nor tailscale can reach Alertmanager's API or the mail relay.
    assert on["alerting"] == {"alertmanager", "smtp-relay", "egress-proxy"}
    assert on["edge"] == {"api", "tailscale"}
    assert set(services["api"]["networks"]) == {"data", "edge", "outbound"}
    assert set(services["tailscale"]["networks"]) == {"edge", "outbound"}
    assert set(services["alertmanager"]["networks"]) == {"alerting", "monitoring"}
    assert set(services["smtp-relay"]["networks"]) == {"alerting"}


def environment(service: dict[str, Any]) -> dict[str, str]:
    """A service's environment as a mapping; compose prints some as `KEY=value` lists."""
    variables = service["environment"]
    return dict(v.split("=", 1) for v in variables) if isinstance(variables, list) else variables


@pytest.mark.integration
def test_each_client_goes_out_through_its_own_port(prod: dict[str, Any]) -> None:
    services = prod["services"]
    for client, (_, network, address) in CLIENTS.items():
        found = services[service(client)]
        (pool,) = prod["networks"][network]["ipam"]["config"]
        subnet, dynamic = (
            ipaddress.ip_network(pool["subnet"]),
            ipaddress.ip_network(pool["ip_range"]),
        )
        # The only address its port serves (test_each_client_has_its_own_port_and_address).
        assert found["networks"][network]["ipv4_address"] == address
        assert ipaddress.ip_address(address) in subnet
        assert ipaddress.ip_address(address) not in dynamic
        assert not found.get("ports")
    for client in ("api", "tailscale"):
        found = services[client]
        assert environment(found)["HTTPS_PROXY"] == f"http://egress-proxy:{CLIENTS[client][0]}"
        assert found["depends_on"]["egress-proxy"]["condition"] == "service_healthy"
    assert environment(services["api"])["NO_PROXY"] == NO_PROXY
    tailscale = environment(services["tailscale"])
    assert tailscale["TS_TAILSCALED_EXTRA_ARGS"] == "--no-logs-no-support"


@pytest.mark.integration
def test_alert_delivery_goes_out_through_its_own_ports(prod: dict[str, Any]) -> None:
    alertmanager, relay = prod["services"]["alertmanager"], prod["services"]["smtp-relay"]
    config = yaml.safe_load(ALERTMANAGER_CONFIG.read_text(encoding="utf-8"))
    (discord,) = config["receivers"][0]["discord_configs"]
    assert (
        discord["http_config"]["proxy_url"] == f"http://egress-proxy:{CLIENTS['alertmanager'][0]}"
    )
    # Alertmanager sends no SMTP through a proxy, so its mail goes to the relay: from Alertmanager's
    # address alone, each connection a CONNECT to Gmail on the relay's own port, idle ones closed.
    assert config["global"]["smtp_smarthost"] == "smtp-relay:2525"
    assert relay["entrypoint"] == [
        "socat",
        "-T60",
        f"TCP4-LISTEN:2525,fork,range={CLIENTS['alertmanager'][2]}/32",
        f"PROXY:egress-proxy:{GMAIL}:587,proxyport={CLIENTS['smtp_relay'][0]}",
    ]
    assert relay["image"].startswith("ghcr.io/kwnhyk04/filinglens-squid:${IMAGE_TAG:?")
    assert alertmanager["depends_on"]["egress-proxy"]["condition"] == "service_healthy"
    for found in (alertmanager, relay):
        assert found["profiles"] == ["observability"]
        assert found["read_only"] is True
        assert found["cap_drop"] == ["ALL"]


@pytest.mark.integration
def test_the_proxy_is_pinned_and_locked_down(prod: dict[str, Any]) -> None:
    proxy = prod["services"]["egress-proxy"]
    assert proxy["image"].startswith("ghcr.io/kwnhyk04/filinglens-squid:${IMAGE_TAG:?")
    assert not proxy.get("ports")
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    mounts = [(Path(v["source"]), v["target"], v.get("read_only")) for v in proxy["volumes"]]
    assert mounts == [(SQUID_CONF, "/etc/squid/squid.conf", True)]


@pytest.fixture(scope="module")
def image(docker: Docker) -> str:
    docker("build", "--tag", IMAGE, str(SQUID))
    return IMAGE


@pytest.fixture(scope="module")
def egress_net(
    image: str,
    docker: Docker,
    run: Run,
    wait_for: WaitFor,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[str]:
    """A throwaway internal network with the proxy on it (`<network>-proxy`, alias egress-proxy),
    and squid.conf's client addresses moved to that network. Yields the network's name."""
    conf = SQUID_CONF.read_bytes()
    for client, address in TEST_ADDRESSES.items():
        production = CLIENTS[client][2].encode()
        assert conf.count(production) == 1  # the swap changes nothing but the client's ACL
        conf = conf.replace(production, address.encode())
    test_conf = tmp_path_factory.mktemp("squid") / "squid.conf"
    test_conf.write_bytes(conf)
    network = f"filinglens-egress-test-{uuid.uuid4().hex[:8]}"
    proxy = f"{network}-proxy"
    subnet, dynamic = TEST_NET
    docker("network", "create", "--internal", "--subnet", subnet, "--ip-range", dynamic, network)
    try:
        mount = f"type=bind,source={test_conf},target=/etc/squid/squid.conf,readonly"
        hosts = [f"--add-host={name}:{address}" for name, address in HOSTS.items()]
        where = ("--name", proxy, "--network", network, "--ip", PROXY)
        alias = ("--network-alias", "egress-proxy")
        docker("run", "--detach", *where, *alias, *HARDENED, "--mount", mount, *hosts, image)
        ports = (port for port, _, _ in CLIENTS.values())
        listening = " && ".join(f"echo > /dev/tcp/127.0.0.1/{port}" for port in ports)
        if not wait_for(lambda: run("exec", proxy, "bash", "-c", listening).returncode == 0):
            pytest.fail(f"squid did not open its ports: {run('logs', proxy).stderr}")
        yield network
    finally:
        run("rm", "--force", proxy)
        run("network", "rm", network)


@pytest.fixture(scope="module")
def probe(egress_net: str, image: str, docker: Docker) -> Probe:
    """probe(address, *specs): runs PROBE from a client at `address` on the throwaway network."""

    def send(address: str, *specs: str) -> dict[str, str]:
        client = ("--rm", "--network", egress_net, "--ip", address, "--env", f"PROXY={PROXY}")
        out = docker("run", *client, "--entrypoint=bash", image, "-c", PROBE, "probe", *specs)
        pairs = (line.rsplit("|", 1) for line in out.splitlines())
        return {spec: code for spec, code in pairs}

    return send


@pytest.mark.integration
def test_squid_reads_the_config_without_a_warning(image: str, run: Run) -> None:
    # FreightAudit's squid once dropped a range from an ACL and said so only in a warning.
    mount = f"type=bind,source={SQUID_CONF},target=/etc/squid/squid.conf,readonly"
    done = run("run", "--rm", "--mount", mount, "--entrypoint", "squid", image, "-k", "parse")
    assert done.returncode == 0, done.stderr
    assert "WARNING" not in done.stdout + done.stderr


def connect(port: int, target: str) -> str:
    return f"{port} CONNECT {target}"


@pytest.mark.integration
def test_the_proxy_refuses_what_it_must(probe: Probe) -> None:
    api = {
        **{connect(3128, f"{host}:443"): ALLOWED for host in API_HOSTS},
        **dict.fromkeys(
            [
                # The PC's own listeners, by name and by address; other private destinations.
                connect(3128, "host.docker.internal:443"),
                connect(3128, "host.docker.internal:5433"),
                connect(3128, "192.168.65.254:443"),
                connect(3128, "127.0.0.1:443"),
                connect(3128, "[::1]:443"),
                # Names only, on 443 only, CONNECT only.
                connect(3128, f"{UNREACHABLE}:443"),
                connect(3128, "example.com:443"),
                connect(3128, "api.groq.com:80"),
                "3128 GET http://api.groq.com/",
                # Tailscale's way out is not the api's, nor is alert delivery's.
                connect(3128, "controlplane.tailscale.com:443"),
                connect(3129, "controlplane.tailscale.com:443"),
                connect(3129, "api.groq.com:443"),
                connect(3128, f"{GMAIL}:587"),
                connect(3128, f"{DISCORD}:443"),
                connect(3130, f"{DISCORD}:443"),
                connect(3131, f"{GMAIL}:587"),
            ],
            REFUSED,
        ),
        # Without the proxy, the internal network leads nowhere.
        "direct host.docker.internal 5433": "closed",
        "direct 192.168.65.254 5433": "closed",
    }
    assert probe(TEST_ADDRESSES["api"], *api) == api

    relays = ("derp1f.tailscale.com", "derp12.tailscale.com")
    tailscale = {
        **{connect(3129, f"{host}:443"): ALLOWED for host in (*TAILSCALE_HOSTS, *relays)},
        **dict.fromkeys(
            [
                connect(3129, "derp99.tailscale.com:443"),  # a relay's name, a private address
                connect(3129, "derp1.tailscale.com.example.org:443"),
                connect(3129, "log.tailscale.com:443"),  # its log upload is off
                connect(3129, "host.docker.internal:443"),
                connect(3128, "api.anthropic.com:443"),
                connect(3128, "controlplane.tailscale.com:443"),
            ],
            REFUSED,
        ),
    }
    assert probe(TEST_ADDRESSES["tailscale"], *tailscale) == tailscale

    alertmanager = {
        connect(3130, f"{DISCORD}:443"): ALLOWED,
        **dict.fromkeys(
            [
                # Discord's webhooks by that one name, on 443, CONNECT only.
                connect(3130, "discordapp.com:443"),
                connect(3130, "canary.discord.com:443"),
                connect(3130, "discord.com.example.org:443"),
                connect(3130, f"{DISCORD}:80"),
                "3130 GET http://discord.com/",
                # Not mail, not the PC, and not another client's way out.
                connect(3130, f"{GMAIL}:587"),
                connect(3130, "host.docker.internal:443"),
                connect(3130, "192.168.65.254:443"),
                connect(3131, f"{GMAIL}:587"),
                connect(3128, f"{DISCORD}:443"),
            ],
            REFUSED,
        ),
    }
    assert probe(TEST_ADDRESSES["alertmanager"], *alertmanager) == alertmanager

    relay = {
        connect(3131, f"{GMAIL}:587"): ALLOWED,
        **dict.fromkeys(
            [
                # Gmail's SMTP with STARTTLS, by that one name and on 587 only.
                connect(3131, f"{GMAIL}:443"),
                connect(3131, f"{GMAIL}:465"),
                connect(3131, f"{GMAIL}:25"),
                connect(3131, "gmail.com:587"),
                connect(3131, "smtp.gmail.com.example.org:587"),
                connect(3131, "host.docker.internal:587"),
                connect(3131, "192.168.65.254:587"),
                connect(3131, f"{DISCORD}:443"),
                connect(3130, f"{DISCORD}:443"),
                connect(3128, f"{GMAIL}:587"),
            ],
            REFUSED,
        ),
    }
    assert probe(TEST_ADDRESSES["smtp_relay"], *relay) == relay

    # Any other container on the network gets nothing on any port.
    hosts = ("api.anthropic.com:443", "controlplane.tailscale.com:443", f"{DISCORD}:443")
    targets = [connect(port, host) for port, _, _ in CLIENTS.values() for host in hosts]
    other = dict.fromkeys([*targets, connect(3131, f"{GMAIL}:587")], REFUSED)
    assert probe(OTHER, *other) == other


@pytest.mark.integration
def test_the_mail_relay_serves_alertmanager_alone(
    egress_net: str, image: str, prod: dict[str, Any], docker: Docker, run: Run, wait_for: WaitFor
) -> None:
    # The relay's own command from compose, with Alertmanager's address moved to the test network.
    production = f"range={CLIENTS['alertmanager'][2]}/32"
    command = prod["services"]["smtp-relay"]["entrypoint"]
    assert sum(arg.count(production) for arg in command) == 1
    test = f"range={TEST_ADDRESSES['alertmanager']}/32"
    command = [arg.replace(production, test) for arg in command]
    relay, proxy = f"{egress_net}-relay", f"{egress_net}-proxy"
    where = ("--name", relay, "--network", egress_net, "--ip", TEST_ADDRESSES["smtp_relay"])
    docker("run", "--detach", *where, *HARDENED, f"--entrypoint={command[0]}", image, *command[1:])
    try:
        listening = ("exec", relay, "bash", "-c", "echo > /dev/tcp/127.0.0.1/2525")
        assert wait_for(lambda: run(*listening).returncode == 0), run("logs", relay).stderr

        def connect_from(address: str) -> None:
            client = ("--rm", "--network", egress_net, "--ip", address, "--entrypoint=bash")
            docker("run", *client, image, "-c", RELAY_CLIENT, TEST_ADDRESSES["smtp_relay"])

        def refused(address: str) -> bool:
            lines = run("logs", relay).stderr.splitlines()
            return any("refusing connection" in line and f" {address}:" in line for line in lines)

        def tunnels() -> list[str]:
            """squid's log lines for the relay's CONNECTs to Gmail (the probes add their own)."""
            lines = run("logs", proxy).stdout.splitlines()
            relayed = f" {TEST_ADDRESSES['smtp_relay']} "
            return [line for line in lines if relayed in line and f"CONNECT {GMAIL}:587" in line]

        before = len(tunnels())
        connect_from(OTHER)
        assert wait_for(lambda: refused(OTHER)), run("logs", relay).stderr
        assert len(tunnels()) == before  # refused before any tunnel
        connect_from(TEST_ADDRESSES["alertmanager"])
        assert wait_for(lambda: len(tunnels()) > before), run("logs", relay).stderr
        new = tunnels()[before:]
        assert len(new) == 1
        assert "/503 " in new[0]  # allowed, then no route on the test network
    finally:
        run("rm", "--force", relay)
