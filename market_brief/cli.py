import argparse
import logging
from datetime import date
from pathlib import Path

from .analytics import run_queries
from .brief import create_brief
from .ingest import backfill, nightly
from .replay import replay_ollama, write_replay_report

LOGGER = logging.getLogger(__name__)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Equities end-of-day pipeline")
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)
    backfill_parser = commands.add_parser("backfill")
    backfill_parser.add_argument("--as-of", type=_date, default=date.today())
    backfill_parser.add_argument("--daily-days", type=int, default=365)
    backfill_parser.add_argument("--minute-days", type=int, default=30)
    nightly_parser = commands.add_parser("nightly")
    nightly_parser.add_argument("--as-of", type=_date, default=date.today())
    brief_parser = commands.add_parser("brief")
    brief_parser.add_argument("--as-of", type=_date, default=date.today())
    all_parser = commands.add_parser("run-all")
    all_parser.add_argument("--as-of", type=_date, default=date.today())
    replay_parser = commands.add_parser("replay-ollama", help="replay historical sessions and count validator outcomes")
    replay_parser.add_argument("--end-as-of", type=_date, default=date.today())
    replay_parser.add_argument("--count", type=int, default=20)
    replay_parser.add_argument("--output", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "backfill":
        LOGGER.info("backfill result: %s", backfill(args.daily_days, args.minute_days, args.as_of))
    elif args.command == "nightly":
        LOGGER.info("nightly result: %s", nightly(args.as_of))
    elif args.command == "replay-ollama":
        report = replay_ollama(args.end_as_of, args.count)
        output = args.output or f"outputs/ollama_replay_{args.end_as_of.isoformat()}.md"
        destination = write_replay_report(report, Path(output))
        LOGGER.info(
            "wrote %s (accepted=%s rejected=%s errors=%s)",
            destination,
            report["accepted"],
            report["rejected"],
            report["errors"],
        )
    else:
        if args.command == "run-all":
            nightly(args.as_of)
        markdown, html, llm_used = create_brief(run_queries(args.as_of), args.as_of)
        LOGGER.info("wrote %s and %s (llm accepted=%s)", markdown, html, llm_used)


if __name__ == "__main__":
    main()
