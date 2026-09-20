import argparse
import json

from collector.adapters.vast import BILLING_MODES, CollectorError
from collector.ingestion_client import IngestionClientError
from collector.runner import run_daemon, sync_all, sync_vast


def main() -> int:
    parser = argparse.ArgumentParser(description="KAI external market collector")
    subcommands = parser.add_subparsers(dest="command", required=True)
    sync = subcommands.add_parser("sync", help="collect and submit one batch")
    sync.add_argument("billing_mode", choices=(*BILLING_MODES, "all"), nargs="?", default="all")
    subcommands.add_parser("run", help="run the long-lived collector scheduler")
    args = parser.parse_args()
    if args.command == "run":
        run_daemon()
        return 0
    try:
        result = sync_all() if args.billing_mode == "all" else sync_vast(args.billing_mode)
    except (CollectorError, IngestionClientError) as exc:
        print(json.dumps({"status": "error", "error": exc.code}))
        return 1
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
