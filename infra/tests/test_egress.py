"""Production's egress proxy (infra/squid, docs/deploy.md): its allowlists, how compose wires it,
and a live check that it refuses what it must (needs Docker).

The live check runs the proxy on a throwaway internal network with no route out, and its
/etc/hosts maps every name the probes ask for, so no request leaves the machine: squid answers an
allowed request with 503 when it finds no route, and refuses the rest with 403.
"""

import ipaddress
import json
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from filinglens_llm.providers import BASE_URLS

ROOT = Path(__file__).parents[2]
SQUID = ROOT / "infra" / "squid"
SQUID_CONF = SQUID / "squid.conf"
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
NO_PROXY = "postgres,redis,rabbitmq,otel-collector,localhost,127.0.0.1,::1"

IMAGE = "filinglens-squid:test"
TEST_NET = ("10.231.233.0/28", "10.231.233.8/29")  # subnet and dynamic range; production's is .232
TEST_ADDRESSES = {"api": "10.231.233.2", "tailscale": "10.231.233.3"}
PROXY, OTHER = "10.231.233.4", "10.231.233.9"
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

type Probe = Callable[..., dict[str, str]]


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


def test_each_client_has_its_own_port_and_address() -> None:
    assert directives("http_port") == [["3128", "name=api"], ["3129", "name=tailscale"]]
    found = acls()
    assert found["from_api"] == [["myportname", "api"]]
    assert found["from_tailscale"] == [["myportname", "tailscale"]]
    assert found["api_ip"] == [["src", "10.231.232.2"]]
    assert found["tailscale_ip"] == [["src", "10.231.232.3"]]


def test_refusals_come_before_the_allowlists() -> None:
    assert directives("http_access") == [
        ["deny", "!CONNECT"],
        ["deny", "!https_port"],
        ["deny", "non_public"],
        ["allow", "from_api", "api_ip", "api_hosts"],
        ["allow", "from_tailscale", "tailscale_ip", "tailscale_hosts"],
        ["allow", "from_tailscale", "tailscale_ip", "tailscale_derp"],
        ["deny", "all"],
    ]
    found = acls()
    assert found["CONNECT"] == [["method", "CONNECT"]]
    assert found["https_port"] == [["port", "443"]]
    assert {line[0] for line in found["non_public"]} == {"dst"}
    ranges = {value for line in found["non_public"] for value in line[1:]}
    private = ["10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12"]
    assert {*private, "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10"} <= ranges


def test_the_allowlists_hold_only_what_production_calls() -> None:
    found = acls()
    assert found["api_hosts"] == [["dstdomain", "-n", *sorted(API_HOSTS)]]
    assert found["tailscale_hosts"] == [["dstdomain", "-n", *sorted(TAILSCALE_HOSTS)]]
    assert found["tailscale_derp"] == [["dstdom_regex", "-n", DERP]]
    # A provider URL that moves in code must move here too.
    assert {urlsplit(BASE_URLS[name]).hostname for name in ("groq", "nvidia")} <= API_HOSTS


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["docker", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,  # the first image build
        check=False,
    )


def docker(*args: str) -> str:
    done = run(*args)
    assert done.returncode == 0, f"docker {args[0]} failed: {done.stderr.strip()}"
    return done.stdout


@pytest.fixture(scope="module")
def prod(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Production's compose model, merged but not interpolated, with every profile's services. The
    env file is empty, so no value of .env or .env.prod is read."""
    empty = tmp_path_factory.mktemp("compose") / "empty.env"
    empty.write_text("", encoding="utf-8")
    files = ("-f", "infra/docker-compose.yml", "-f", "infra/docker-compose.prod.yml")
    profiles = ("--profile", "ingest", "--profile", "observability", "--profile", "test")
    options = ("config", "--no-interpolate", "--format", "json")
    return json.loads(docker("compose", "--env-file", str(empty), *files, *profiles, *options))


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
    assert on["outbound"] == {"api", "tailscale", "egress-proxy"}
    assert on["edge"] == {"api", "tailscale"}
    assert set(services["api"]["networks"]) == {"data", "edge", "outbound"}
    assert set(services["tailscale"]["networks"]) == {"edge", "outbound"}


def environment(service: dict[str, Any]) -> dict[str, str]:
    """A service's environment as a mapping; compose prints some as `KEY=value` lists."""
    variables = service["environment"]
    return dict(v.split("=", 1) for v in variables) if isinstance(variables, list) else variables


@pytest.mark.integration
def test_each_client_goes_out_through_its_own_port(prod: dict[str, Any]) -> None:
    services = prod["services"]
    (pool,) = prod["networks"]["outbound"]["ipam"]["config"]
    subnet, dynamic = ipaddress.ip_network(pool["subnet"]), ipaddress.ip_network(pool["ip_range"])
    for client, port in (("api", 3128), ("tailscale", 3129)):
        service = services[client]
        address = service["networks"]["outbound"]["ipv4_address"]
        assert acls()[f"{client}_ip"] == [["src", address]]  # the only address its port serves
        assert ipaddress.ip_address(address) in subnet
        assert ipaddress.ip_address(address) not in dynamic
        assert environment(service)["HTTPS_PROXY"] == f"http://egress-proxy:{port}"
        assert service["depends_on"]["egress-proxy"]["condition"] == "service_healthy"
        assert not service.get("ports")
    assert environment(services["api"])["NO_PROXY"] == NO_PROXY
    tailscale = environment(services["tailscale"])
    assert tailscale["TS_TAILSCALED_EXTRA_ARGS"] == "--no-logs-no-support"


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
def image() -> str:
    docker("build", "--tag", IMAGE, str(SQUID))
    return IMAGE


@pytest.fixture(scope="module")
def probe(image: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Probe]:
    """probe(address, *specs): runs PROBE from a client at `address` on a throwaway network, with
    squid.conf's client addresses moved to the test network."""
    conf = SQUID_CONF.read_bytes()
    for client, address in TEST_ADDRESSES.items():
        production = acls()[f"{client}_ip"][0][1].encode()
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
        docker("run", "--detach", *where, *HARDENED, "--mount", mount, *hosts, image)
        listening = "echo > /dev/tcp/127.0.0.1/3128 && echo > /dev/tcp/127.0.0.1/3129"
        for _ in range(60):
            if run("exec", proxy, "bash", "-c", listening).returncode == 0:
                break
            time.sleep(0.5)
        else:
            pytest.fail(f"squid did not open its ports: {run('logs', proxy).stderr}")

        def send(address: str, *specs: str) -> dict[str, str]:
            client = ("--rm", "--network", network, "--ip", address, "--env", f"PROXY={PROXY}")
            out = docker("run", *client, "--entrypoint=bash", image, "-c", PROBE, "probe", *specs)
            pairs = (line.rsplit("|", 1) for line in out.splitlines())
            return {spec: code for spec, code in pairs}

        yield send
    finally:
        run("rm", "--force", proxy)
        run("network", "rm", network)


@pytest.mark.integration
def test_squid_reads_the_config_without_a_warning(image: str) -> None:
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
                # Tailscale's way out is not the api's.
                connect(3128, "controlplane.tailscale.com:443"),
                connect(3129, "controlplane.tailscale.com:443"),
                connect(3129, "api.groq.com:443"),
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

    # Any other container on the network gets nothing on either port.
    hosts = ("api.anthropic.com:443", "controlplane.tailscale.com:443")
    other = dict.fromkeys([connect(port, host) for port in (3128, 3129) for host in hosts], REFUSED)
    assert probe(OTHER, *other) == other
