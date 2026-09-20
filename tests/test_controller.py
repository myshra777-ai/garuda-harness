from harness.controller import main


def test_help_path_returns_zero() -> None:
    assert main([]) == 0


def test_check_is_read_only() -> None:
    assert main(["check"]) == 0


def test_run_requires_read_only() -> None:
    assert main(["run"]) == 2


def test_read_only_run_is_allowed() -> None:
    assert main(["run", "--read-only"]) == 0
