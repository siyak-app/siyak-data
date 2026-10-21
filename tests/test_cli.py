import pytest

from pipeline.cli import build_parser, main


def test_every_command_is_registered() -> None:
    parser = build_parser()
    for command in ["fetch", "build", "validate", "manifest", "check-updates"]:
        args = parser.parse_args([command])
        assert args.command == command


def test_missing_command_exits_with_usage() -> None:
    with pytest.raises(SystemExit):
        main([])
