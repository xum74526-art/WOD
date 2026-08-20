from __future__ import annotations

from app.services.market_snapshots import refresh_getdeploying_public_snapshot


def main() -> None:
    payload = refresh_getdeploying_public_snapshot()
    print(
        "GetDeploying public snapshot refreshed: "
        f"{len(payload['models'])} models, {len(payload['history'])} price points, "
        f"updated {payload['source_updated_at']}"
    )


if __name__ == "__main__":
    main()
