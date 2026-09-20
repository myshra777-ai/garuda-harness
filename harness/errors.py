"""Typed errors for the Garuda Harness MCP transport."""


class HarnessError(Exception):
    """Base error for harness failures."""


class TransportError(HarnessError):
    """The MCP process or stdio transport failed."""


class ProtocolError(HarnessError):
    """The MCP peer returned an invalid or unexpected message."""


class ReadOnlyViolation(HarnessError):
    """A mutating tool was requested in H1 read-only mode."""


class CallTimeout(TransportError):
    """An MCP call exceeded its deadline."""
