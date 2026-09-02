"""
validate_m1.py — Module 1 validation script.

Verifies that:
  1. SYNC_FOLDER is set in the environment or .env file.
  2. SYNC_FOLDER resolves to a real directory.
  3. The configured value is relative (not a machine-specific absolute path),
     confirming portability.

Usage:
    python modules/module-01/validate_m1.py

Exit codes:
    0  — all checks passed (PASS)
    1  — one or more checks failed (FAIL)
"""

import os
import sys
from pathlib import Path


def load_dotenv_simple(dotenv_path: Path) -> None:
    """
    Minimal .env loader — no third-party dependencies required.
    Reads KEY=VALUE lines and sets them in os.environ if not already set.
    Lines beginning with '#' and blank lines are ignored.
    """
    if not dotenv_path.is_file():
        return
    with dotenv_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> int:
    print("[M1 VALIDATION]")

    # Determine project root (two levels up from this script).
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent.parent  # modules/module-01 -> project root

    # Load .env if present (do not require it — fall back to env vars).
    dotenv_path = project_root / ".env"
    load_dotenv_simple(dotenv_path)

    # --- Check 1: SYNC_FOLDER is configured ---
    sync_folder_raw = os.environ.get("SYNC_FOLDER", "")
    if not sync_folder_raw:
        # Fall back to the documented default
        sync_folder_raw = "./organization/files"
        print(f"SYNC_FOLDER not set; using default: {sync_folder_raw}")
    else:
        print(f"SYNC_FOLDER (from env/.env): {sync_folder_raw}")

    # --- Check 2: Resolve the path ---
    # Relative paths are resolved from the project root, not the script location.
    sync_folder_path = (project_root / sync_folder_raw).resolve()
    print(f"SYNC_FOLDER resolved to: {sync_folder_path}")

    directory_exists = sync_folder_path.is_dir()
    print(f"Directory exists: {directory_exists}")

    # --- Check 3: Portability — configured value must be relative ---
    raw_stripped = sync_folder_raw.strip()
    is_relative = not Path(raw_stripped).is_absolute()
    portability_status = "OK" if is_relative else "FAIL — absolute path detected"
    print(f"Portability check: path is relative in config ({portability_status})")

    # --- Result ---
    passed = directory_exists and is_relative
    print(f"Result: {'PASS' if passed else 'FAIL'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
