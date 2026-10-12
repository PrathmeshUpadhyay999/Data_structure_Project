"""Run the Flask heatwave dashboard from the project root.

    python -m heatwave_dashboard.server --port 5000
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from heatwave_pipeline import config

from . import create_app


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Heatwave monitoring dashboard.")
    parser.add_argument("--db", default=str(config.DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="port (default 5000)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    try:
        app = create_app(args.db)
    except (FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Dashboard running at http://{args.host}:{args.port} (db: {args.db}). Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
