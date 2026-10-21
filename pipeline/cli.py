"""Command-line entry point: ``uv run siyak-data <command>``.

argparse (standard library) is used instead of typer: the CLI has five flat
subcommands, needs no runtime dependency and type-checks under ``mypy --strict``
without plugins.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence

from pipeline.build import run_build
from pipeline.build_pricing import build_pricing
from pipeline.errors import PipelineError
from pipeline.fetch import fetch_sources
from pipeline.manifest import build_manifest, write_manifest
from pipeline.paths import dist_dir, repo_root
from pipeline.sources import Source, load_all
from pipeline.updates import check_source
from pipeline.validate import print_report, run_validate


def _selected_sources(args: argparse.Namespace) -> list[Source]:
    sources = load_all()
    wanted: list[str] = args.source or []
    if not wanted:
        return sources
    unknown = sorted(set(wanted) - {s.id for s in sources})
    if unknown:
        raise PipelineError(f"unknown source id(s): {', '.join(unknown)}")
    return [s for s in sources if s.id in wanted]


def cmd_fetch(args: argparse.Namespace) -> None:
    """Download and verify the pinned files of every (or the selected) source."""
    results = fetch_sources(_selected_sources(args), pin=args.pin)
    for r in results:
        print(f"{r.status:10}  {r.source_id}/{r.name}  {r.sha256}")
    unpinned = [r for r in results if r.status == "unpinned"]
    if unpinned:
        print(
            f"\n{len(unpinned)} file(s) are not pinned. Review them in .cache/, then copy the "
            "sha256 above into the matching source.toml by hand."
        )


def cmd_check_updates(args: argparse.Namespace) -> None:
    """Report upstream changes since the pinned versions."""
    for source in _selected_sources(args):
        for report in check_source(source):
            print(f"{report.status:10}  {report.source_id}/{report.name}")
            for line in report.detail:
                print(f"            {line}")


FIXTURES = repo_root() / "tests" / "fixtures"


def apply_profile(profile: str) -> None:
    """Point sources, cache and dist at the committed fixtures for ``--profile fixtures``."""
    if profile == "fixtures":
        os.environ["SIYAK_DATA_SOURCES"] = str(FIXTURES / "sources")
        os.environ["SIYAK_DATA_CACHE"] = str(FIXTURES / "cache")
        os.environ.setdefault("SIYAK_DATA_DIST", str(repo_root() / "dist" / "fixtures"))


def cmd_build(args: argparse.Namespace) -> None:
    """Build core.db and every translation pack into dist/."""
    apply_profile(args.profile)
    for path in run_build():
        print(f"built  {path}  {path.stat().st_size:,} bytes")


def cmd_validate(args: argparse.Namespace) -> None:
    """Run the validation gates on dist/."""
    apply_profile(args.profile)
    report = run_validate(dist_dir(), args.profile)
    print_report(report, dist_dir() / "validation-report.txt")
    if report.failures:
        raise PipelineError("validation failed")


def cmd_manifest(args: argparse.Namespace) -> None:
    """Write dist/manifest.json and dist/pricing.json."""
    apply_profile(args.profile)
    dist = dist_dir()
    manifest, warnings = build_manifest(load_all(), dist, tag=args.tag)
    for warning in warnings:
        print(f"warning  {warning}")
    print(f"wrote  {write_manifest(manifest, dist / 'manifest.json')}")
    print(f"wrote  {build_pricing(dist / 'pricing.json')}")


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="siyak-data", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download pinned sources into .cache/ and verify sha256")
    fetch.add_argument(
        "--pin",
        action="store_true",
        help="also download unpinned files and print their sha256 (writes nothing)",
    )
    fetch.add_argument("--source", action="append", help="only this source id (repeatable)")
    fetch.set_defaults(func=cmd_fetch)

    build = sub.add_parser("build", help="build core.db and packs into dist/")
    build.add_argument("--profile", choices=["full", "fixtures"], default="full")
    build.set_defaults(func=cmd_build)

    validate = sub.add_parser("validate", help="run the validation gates on dist/")
    validate.add_argument("--profile", choices=["full", "fixtures"], default="full")
    validate.set_defaults(func=cmd_validate)

    manifest = sub.add_parser("manifest", help="write dist/manifest.json and dist/pricing.json")
    manifest.add_argument("--profile", choices=["full", "fixtures"], default="full")
    manifest.add_argument("--tag", help="release tag used in pack URLs (default: $SIYAK_DATA_TAG)")
    manifest.set_defaults(func=cmd_manifest)

    check = sub.add_parser("check-updates", help="list upstream changes since the pinned versions")
    check.add_argument("--source", action="append", help="only this source id (repeatable)")
    check.set_defaults(func=cmd_check_updates)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    func: Callable[[argparse.Namespace], None] = args.func
    try:
        func(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
