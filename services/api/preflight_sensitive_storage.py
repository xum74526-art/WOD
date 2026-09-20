"""Read-only startup preflight for persistent sensitive-data keys.

This module deliberately imports no database package or application model. It
must run before every schema check or migration so an unsafe key configuration
cannot mutate even an otherwise unrelated table.
"""

import sys

from app.core.sensitive import assert_sensitive_storage_secure


def main() -> int:
    try:
        assert_sensitive_storage_secure()
    except RuntimeError as exc:
        print(f"[sensitive-storage-preflight] refused: {exc}", file=sys.stderr)
        return 1
    print("[sensitive-storage-preflight] secure storage configuration ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
