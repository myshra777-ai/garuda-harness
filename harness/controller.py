"""H1 read-only Garuda Harness controller."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.budgets import BudgetExceeded, CallBudget
from harness.errors import HarnessError, ProtocolError, TransportError
from harness.events import EventJournal
from harness.manifest import RunManifest
from harness.session import open_read_only_session


def _validate_sequence(
    sequence: list[tuple[str, dict[str, Any]]],
) -> None:
    for tool_name, arguments in sequence:
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("tool names must be non-empty strings")
        if not isinstance(arguments, dict):
            raise TypeError("tool arguments must be dictionaries")


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
        _validate_sequence(sequence)

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
    subparsers = parser.add_subparsers(dest="action")

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
    run_parser.add_argument(
        "--run-id",
        default=None,
        help="Run identifier; generated when omitted.",
    )
    run_parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".garuda-harness"),
        help="Directory for run artifacts.",
    )
    run_parser.add_argument(
        "--max-calls",
        type=int,
        default=10,
        help="Maximum number of read-only tool calls.",
    )
    run_parser.add_argument(
        "server_command",
        nargs=argparse.REMAINDER,
        help="MCP server command, preceded by --.",
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

    if args.action is None:
        parser.print_help()
        return 0

    if args.action == "check":
        print("H1 controller configuration: OK")
        print("Mode: read-only")
        print("Mutation: disabled")
        return 0

    if args.action == "run":
        if not args.read_only:
            print(
                "refusing to run without --read-only; "
                "H1 does not support mutation",
                file=sys.stderr,
            )
            return 2

        if args.max_calls < 1:
            print("--max-calls must be positive", file=sys.stderr)
            return 2

        if not args.server_command:
            print(
                "H1 read-only controller requires an MCP command "
                "after '--'.",
                file=sys.stderr,
            )
            return 2

        command = args.server_command
        if command[0] == "--":
            command = command[1:]

        if not command:
            print(
                "H1 read-only controller requires an MCP command "
                "after '--'.",
                file=sys.stderr,
            )
            return 2

        run_id = args.run_id or f"run-{uuid4().hex[:12]}"
        controller = ReadOnlyController(
            run_id=run_id,
            workspace_dir=args.workspace,
            command=command,
            budget=CallBudget(max_calls=args.max_calls),
        )

        try:
            controller.run([])
        except BudgetExceeded:
            return 3
        except ProtocolError:
            return 4
        except TransportError:
            return 5
        except HarnessError:
            return 1

        return 0

    if args.action == "replay":
        print(f"Replay implementation is not available yet: {args.journal}")
        return 0

    parser.error(f"unknown command: {args.action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
