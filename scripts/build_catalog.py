"""Build uirizz_plugin/catalogs/uirizz_v1.json from the Basic Catalog + uirizz_components.json.

Run after changing uirizz_components.json or upgrading a2ui-agent-sdk:
    python scripts/build_catalog.py          # write
    python scripts/build_catalog.py --check  # exit 1 if the committed file is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "uirizz_plugin" / "catalogs" / "uirizz_components.json"
OUT = ROOT / "uirizz_plugin" / "catalogs" / "uirizz_v1.json"


def build() -> dict:
    from a2ui.core.basic_catalog import BasicCatalog, ProtocolVersion

    doc = BasicCatalog(ProtocolVersion.V1_0).to_json()
    extra = json.loads(SRC.read_text(encoding="utf-8"))
    cid = extra["catalogId"]
    doc["$id"] = cid
    doc["catalogId"] = cid
    doc["title"] = extra["title"]
    doc["instructions"] = doc.get("instructions", "") + "\n\n## uirizz components\n\n" + extra["instructions"]
    union = doc["$defs"]["anyComponent"]["oneOf"]
    for name, schema in extra["components"].items():
        if name in doc["components"]:
            raise SystemExit(f"{name} already exists in the Basic Catalog")
        doc["components"][name] = schema
        union.append({"$ref": f"#/components/{name}"})
    return doc


def main(argv: list[str]) -> int:
    text = json.dumps(build(), indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != text:
            print(f"{OUT.name} is stale; run python scripts/build_catalog.py")
            return 1
        print(f"{OUT.name} is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
