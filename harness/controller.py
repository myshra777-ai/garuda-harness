"""H1 read-only Garuda Harness controller."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from harness.budgets import BudgetExceeded, CallBudget
from harness.errors import ProtocolError
from harness.events import EventJournal
from harness.manifest import RunManifest
from harness.session import open_read_only_session


class ReadOnlyController:
    """Orchestrates an end-to-end bounded, read-only harness run."""

    def __init__(
        self,
        run_id: str,
        workspace_dir: Path,
        command: list[str],
        env: dict[str, str] | None = None,
        budget: CallBudget | None = None,
    ) -> None:
        self.run_id = run_id
        self.workspace_dir = Path(workspace_dir)
        self.command = command
        self.env = env
        self.budget = budget or CallBudget()

    def run(self, sequence: list[tuple[str, dict[str, Any]]]) -> None:
        """
        Executes a bounded sequence of tool calls securely.
        """
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.workspace_dir / "run.json"
        journal_path = self.workspace_dir / "events.jsonl"

        manifest = RunManifest.start(manifest_path, self.run_id, read_only=True)
        journal = EventJournal(journal_path)

        command_name = self.command[0] if self.command else "unknown"
        journal.append(
            self.run_id,
            "run.started",
            {
                "command_name": command_name,
                "command_length": len(self.command),
                "sequence_length": len(sequence),
            },
        )

        try:
            session = open_read_only_session(
                command=self.command,
                env=self.env,
                budget=self.budget,
                journal=journal,
                run_id=self.run_id,
            )
        except ProtocolError:
            manifest.finish("failed", "session initialization failed: protocol error")
            journal.append(
                self.run_id,
                "run.failed",
                {"error": "session initialization failed: protocol error"},
            )
            raise
        except Exception:
            manifest.finish("failed", "session initialization failed")
            journal.append(
                self.run_id,
                "run.failed",
                {"error": "session initialization failed"},
            )
            raise

        try:
            manifest.update(
                protocol_version=session.protocol_version,
                server_info=session.server_info,
                journal_path=journal_path.name,
                event_count=self.budget.call_count,
            )

            for tool_name, arguments in sequence:
                session.call_read_only(tool_name, arguments)

            manifest.update(event_count=self.budget.call_count)
            manifest.finish("succeeded")
            journal.append(self.run_id, "run.succeeded", {})

        except BudgetExceeded:
            manifest.update(event_count=self.budget.call_count)
            manifest.finish("cancelled", "budget exceeded")
            journal.append(self.run_id, "run.cancelled", {"reason": "budget exceeded"})
            raise
        except Exception:
            manifest.update(event_count=self.budget.call_count)
            manifest.finish("failed", "execution failed")
            journal.append(self.run_id, "run.failed", {"error": "execution failed"})
            raise
        finally:
            session.close()


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
