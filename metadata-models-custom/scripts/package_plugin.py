#!/usr/bin/env python3
"""
scripts/package_plugin.py
--------------------------
Pure-Python fallback to build the DataHub custom model plugin zip WITHOUT
needing Java or Gradle installed.

The DataHub GMS plugin loader only needs:
  <plugin-root>/
    entity-registry.yaml
    com/anamnesis/incident/IncidentMemory.pdl

This script creates that zip and optionally installs it.

Usage:
    python scripts/package_plugin.py            # build only
    python scripts/package_plugin.py --install  # build + install to ~/.datahub
    python scripts/package_plugin.py --install --version 0.1.0
"""

import argparse
import os
import pathlib
import shutil
import zipfile

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGISTRY_ID = "anamnesis-incident-model"

SCRIPT_DIR  = pathlib.Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent        # metadata-models-custom/
DIST_DIR    = PROJECT_DIR / "build" / "dist"

REGISTRY_FILE = PROJECT_DIR / "registry" / "entity-registry.yaml"
PEGASUS_DIR   = PROJECT_DIR / "src" / "main" / "pegasus"


def build_zip(version: str) -> pathlib.Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / f"metadata-models-custom-{version}.zip"

    print(f"[BUILD] Building plugin zip -> {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. entity-registry.yaml at zip root
        if not REGISTRY_FILE.exists():
            raise FileNotFoundError(f"Registry not found: {REGISTRY_FILE}")
        zf.write(REGISTRY_FILE, "entity-registry.yaml")
        print(f"   + entity-registry.yaml")

        # 2. All PDL files preserving package-relative paths
        for pdl in PEGASUS_DIR.rglob("*.pdl"):
            arcname = pdl.relative_to(PEGASUS_DIR)
            zf.write(pdl, str(arcname))
            print(f"        + {arcname}")

    print(f"[OK] Zip created: {zip_path}")
    return zip_path


def install_zip(zip_path: pathlib.Path, version: str) -> None:
    home = pathlib.Path.home()
    dest = home / ".datahub" / "plugins" / "models" / REGISTRY_ID / version
    dest.mkdir(parents=True, exist_ok=True)

    print(f"[INSTALL] Installing to: {dest}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)

    print("[OK] Plugin installed.")
    print(f"   Path: {dest}")
    print()
    print("   Next steps:")
    print("   1. Restart the DataHub GMS container:")
    print("      docker restart datahub-datahub-gms-1")
    print("   2. Verify the model loaded:")
    print("      curl -s http://localhost:8080/config")
    print(f"      Look for '{REGISTRY_ID}' with loadResult: SUCCESS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Package DataHub custom model plugin")
    parser.add_argument("--install", action="store_true", help="Install after building")
    parser.add_argument("--version", default="0.0.0-dev", help="Plugin version string")
    args = parser.parse_args()

    zip_path = build_zip(args.version)
    if args.install:
        install_zip(zip_path, args.version)
    else:
        print()
        print("   To install:  python scripts/package_plugin.py --install")
        print(f"   Zip path:    {zip_path}")


if __name__ == "__main__":
    main()
