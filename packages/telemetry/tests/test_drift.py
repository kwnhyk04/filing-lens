"""The dashboards and alert rules name only metrics FilingLens records (metrics.SPECS, as the
collector's Prometheus exporter names them) and only the provisioned Grafana datasources.

Third-party names (FastAPI's, RabbitMQ's, the collector's httpcheck) are checked against the names
and label names of a /metrics capture from the live check, once that capture exists.
"""

import json
import re
from pathlib import Path

import pytest

from filinglens_telemetry.metrics import SPECS

INFRA = Path(__file__).parents[3] / "infra"
CAPTURE = Path(__file__).with_name("fixtures") / "metrics-capture.txt"  # `name label,label`
OURS = re.compile(r"\b(?:filinglens|gen_ai)_\w+")
THEIRS = re.compile(r"\b((?:http_server|rabbitmq|httpcheck)_\w+|target_info)(?:\{([^}]*)\})?")


def _exporter_names() -> set[str]:
    """SPECS after the exporter: dots become underscores, unit s adds _seconds and a {...} unit
    adds nothing, counters end in _total and histograms in _bucket, _sum and _count."""
    names: set[str] = set()
    for name, unit, kind in SPECS:
        base = name.replace(".", "_") + ("_seconds" if unit == "s" else "")
        if kind == "counter":
            names.add(f"{base}_total")
        elif kind == "histogram":
            names |= {f"{base}_{suffix}" for suffix in ("bucket", "sum", "count")}
        else:
            names.add(base)
    return names


def _dashboards() -> list[tuple[Path, dict[str, object]]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((INFRA / "dashboards").glob("*.json"))
    ]


def _expressions() -> list[str]:
    """Every PromQL expression: the dashboards' targets, and the alert rules' file as text."""
    found = [
        target["expr"]
        for _, dashboard in _dashboards()
        for panel in dashboard["panels"]  # pyright: ignore[reportGeneralTypeIssues]
        for target in panel["targets"]
    ]
    return [*found, (INFRA / "prometheus-alerts.yml").read_text(encoding="utf-8")]


def test_units_are_seconds_an_annotation_or_none() -> None:
    """The exporter's names above depend on it."""
    assert all(unit in ("s", "") or re.fullmatch(r"\{\w+\}", unit) for _, unit, _ in SPECS)


def _metric_names(expr: str) -> list[str]:
    """Our metric names in an expression; label names (by (...), {...}) are left out."""
    expr = re.sub(r"\b(?:by|without|on|ignoring)\s*\([^)]*\)", "", expr)
    return OURS.findall(re.sub(r"\{[^}]*\}", "", expr))


def test_dashboards_and_alerts_name_only_recorded_metrics() -> None:
    used = {name for expr in _expressions() for name in _metric_names(expr)}
    assert len(used) > 20  # the paths still lead to the files
    assert used - _exporter_names() == set()


def test_three_dashboards_on_provisioned_datasources_only() -> None:
    provisioned = set(
        re.findall(r"uid: (\S+)", (INFRA / "grafana-datasources.yaml").read_text(encoding="utf-8"))
    )
    dashboards = _dashboards()
    assert [path.name for path, _ in dashboards] == [
        "answers.json",
        "ingest.json",
        "service-health.json",
    ]
    for path, dashboard in dashboards:
        for panel in dashboard["panels"]:  # pyright: ignore[reportGeneralTypeIssues]
            assert panel["datasource"]["uid"] in provisioned, (path.name, panel["title"])


@pytest.mark.skipif(not CAPTURE.exists(), reason="the live check saves the /metrics capture")
def test_third_party_names_and_labels_match_the_live_capture() -> None:
    captured: dict[str, set[str]] = {}
    for line in CAPTURE.read_text(encoding="utf-8").splitlines():
        name, _, labels = line.partition(" ")
        captured.setdefault(name, set()).update(filter(None, labels.split(",")))
    for expr in _expressions():
        for name, selector in THEIRS.findall(expr):
            assert name in captured, name
            for label in re.findall(r"(\w+)\s*[=!]~?\s*\"", selector):
                assert label in captured[name], (name, label)
