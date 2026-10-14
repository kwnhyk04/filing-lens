"""Export the API contracts for codegen and drift checks: `python -m filinglens_api.contracts`."""

import json
from pathlib import Path

from filinglens_api.main import app, schema

OUT = Path("contracts")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    openapi = json.dumps(app.openapi(), indent=2) + "\n"
    (OUT / "openapi.json").write_text(openapi, encoding="utf-8", newline="\n")
    (OUT / "schema.graphql").write_text(schema.as_str() + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
