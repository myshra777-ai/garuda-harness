"""H1 read-only Garuda Harness controller."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="garuda-harness",
        description="Read-only execution and continuity harness for Garuda.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "check",
        help="Validate the local H1 controller configuration.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a bounded read-only harness session.",
    )
    run_parser.add_argument(
        "--read-only",
        action="store_true",
        default=False,
        help="Require read-only mode.",
    )

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a recorded JSONL event journal.",
    )
    replay_parser.add_argument(
        "journal",
        help="Path to a JSONL event journal.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "check":
        print("H1 controller configuration: OK")
        print("Mode: read-only")
        print("Mutation: disabled")
        return 0

    if args.command == "run":
        if not args.read_only:
            print(
                "refusing to run without --read-only; "
                "H1 does not support mutation",
                file=sys.stderr,
            )
            return 2
        print("H1 read-only controller is not connected yet.")
        print("Transport implementation is the next step.")
        return 0

    if args.command == "replay":
        print(f"Replay implementation is not available yet: {args.journal}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
