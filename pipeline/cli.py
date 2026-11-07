"""Command-line entry point: ``uv run siyak-data <command>``.

argparse (standard library) is used instead of typer: the CLI has a few flat
subcommands, needs no runtime dependency and type-checks under ``mypy --strict``
without plugins.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence

from pipeline.api_embedding import RateLimit
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
    manifest, warnings = build_manifest(
        load_all(), dist, tag=args.tag, unpublished=args.unpublished
    )
    for warning in warnings:
        print(f"warning  {warning}")
    print(f"wrote  {write_manifest(manifest, dist / 'manifest.json')}")
    print(f"wrote  {build_pricing(dist / 'pricing.json')}")


def cmd_eval_embeddings(args: argparse.Namespace) -> None:
    """Compare embedding models and verse texts on data/eval/semantic.toml."""
    from pipeline.embedding import MODELS, VARIANTS  # noqa: PLC0415
    from pipeline.eval_embeddings import run_eval, run_pack_eval  # noqa: PLC0415

    if args.pack:
        out = dist_dir() / "reports" / "embedding-eval-packs.md"
        run_pack_eval(load_all(), args.pack, dist_dir(), out, limit=_rate_limit(args))
    else:
        out = dist_dir() / "reports" / "embedding-eval.md"
        run_eval(args.model or list(MODELS), args.text or list(VARIANTS), out)
    print(f"wrote  {out}")


def _rate_limit(args: argparse.Namespace) -> RateLimit:
    return RateLimit(rpm=args.api_rpm, tpm=args.api_tpm)


def _add_rate_limit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-rpm", type=int, help="requests per minute the embedding API account allows"
    )
    parser.add_argument(
        "--api-tpm", type=int, help="tokens per minute the embedding API account allows"
    )


def cmd_build_embeddings(args: argparse.Namespace) -> None:
    """Build the model and vector packs into dist/ (needs --group embed)."""
    from pipeline.build_embeddings import (  # noqa: PLC0415
        build_model_pack,
        build_vector_pack,
        write_reference,
    )
    from pipeline.schema import build_epoch, build_timestamp  # noqa: PLC0415

    sources = [s for s in load_all() if s.pack is not None]
    models = {s.pack.id: s for s in sources if s.pack and s.pack.type == "model"}
    vectors = [s for s in sources if s.pack and s.pack.type == "vectors"]
    wanted: list[str] = args.pack or []
    unknown = sorted(set(wanted) - set(models) - {s.pack.id for s in vectors if s.pack})
    if unknown:
        raise PipelineError(f"unknown model or vector pack(s): {', '.join(unknown)}")
    out = dist_dir()
    out.mkdir(parents=True, exist_ok=True)
    built_at, mtime = build_timestamp(), build_epoch()
    for pack_id, source in sorted(models.items()):
        if (wanted and pack_id not in wanted) or (args.published and not _published(source)):
            continue
        for path in build_model_pack(source, out, built_at=built_at, mtime=mtime):
            print(f"built  {path}  {path.stat().st_size:,} bytes")
        reference = write_reference(source, out, out / "model-tests" / pack_id)
        print(f"wrote  {reference}")
    for source in vectors:
        if wanted and source.pack and source.pack.id not in wanted:
            continue
        if args.published and not _published(source):
            continue
        built = build_vector_pack(source, models, out, built_at=built_at, limit=_rate_limit(args))
        for path in built:
            print(f"built  {path}  {path.stat().st_size:,} bytes")


def _published(source: Source) -> bool:
    return source.pack is not None and source.pack.publish


def cmd_export_vectors(args: argparse.Namespace) -> None:
    """Write built verse vectors to dist/inputs/ for pinning (pack-format §4.9)."""
    import json  # noqa: PLC0415

    from pipeline.build_embeddings import (  # noqa: PLC0415
        PREBUILT,
        VECTOR_INPUTS_TAG,
        export_vectors,
    )

    by_id = {s.pack.id: s for s in load_all() if s.pack and s.pack.type == "vectors"}
    wanted: list[str] = args.pack or sorted(i for i, s in by_id.items() if _published(s))
    unknown = sorted(set(wanted) - set(by_id))
    if unknown:
        raise PipelineError(f"unknown vector pack(s): {', '.join(unknown)}")
    template = json.loads((repo_root() / "manifest.template.json").read_text(encoding="utf-8"))
    dest = dist_dir() / "inputs"
    for pack_id in wanted:
        source = by_id[pack_id]
        out, sha = export_vectors(source, dist_dir(), dest)
        url = template["release_download_url"].format(tag=VECTOR_INPUTS_TAG, file=out.name)
        print(f"wrote  {out}  {out.stat().st_size:,} bytes")
        print(f"\n# add to {source.path.relative_to(repo_root())}:")
        print("[[files]]")
        print(f'name = "{PREBUILT}"')
        print(f'url = "{url}"')
        print(f'version = "{source.pack.version if source.pack else ""}"')
        print(f'sha256 = "{sha}"')
        print('note = "Verse vectors computed once by a maintainer (export-vectors)."\n')
    print(
        f"Upload the files to the '{VECTOR_INPUTS_TAG}' release, e.g.\n"
        f"  gh release upload {VECTOR_INPUTS_TAG} {dest}/*.npy"
    )


def _audio_sources(args: argparse.Namespace) -> list[Source]:
    by_id = {s.pack.id: s for s in load_all() if s.pack and s.pack.type == "audio"}
    wanted: list[str] = args.pack or sorted(by_id)
    unknown = sorted(set(wanted) - set(by_id))
    if unknown:
        raise PipelineError(f"unknown audio pack(s): {', '.join(unknown)}")
    return [by_id[i] for i in wanted]


def cmd_fetch_audio(args: argparse.Namespace) -> None:
    """Download (and with --pin, list and pin) the upstream files of audio packs."""
    from pipeline.build_audio import fetch_audio  # noqa: PLC0415

    for source in _audio_sources(args):

        def progress(done: int, total: int, pack_id: str = source.id) -> None:
            if done % 500 == 0 or done == total:
                print(f"  {pack_id}: {done}/{total}", flush=True)

        dest = fetch_audio(source, pin=args.pin, workers=args.workers, progress=progress)
        print(f"fetched  {source.id}  {dest}", flush=True)


def cmd_build_audio(args: argparse.Namespace) -> None:
    """Build, check and (with --drop-upstream) clean up audio packs, one at a time."""
    from pipeline.build_audio import (  # noqa: PLC0415
        build_audio_pack,
        check_audio_pack,
        drop_upstream,
        fetch_audio,
    )
    from pipeline.schema import build_epoch, build_timestamp  # noqa: PLC0415

    out = dist_dir()
    built_at, mtime = build_timestamp(), build_epoch()
    for source in _audio_sources(args):
        pack = source.pack
        assert pack is not None
        if args.skip_built and (out / f"{pack.id}.tar.zst").exists():
            print(f"skip   {pack.id} (built)", flush=True)
            continue
        if args.fetch:
            fetch_audio(source, pin=args.pin, workers=args.workers)
        for path in build_audio_pack(source, out, built_at=built_at, mtime=mtime):
            print(f"built  {path}  {path.stat().st_size:,} bytes", flush=True)
        problems = check_audio_pack(out / f"{pack.id}.tar.zst", pack.id, pack.version)
        for problem in problems[:20]:
            print(f"  FAIL {problem}")
        if problems:
            raise PipelineError(f"{pack.id}: {len(problems)} problem(s)")
        print(f"ok     {pack.id}", flush=True)
        if args.drop_upstream:
            drop_upstream(source)


def cmd_pin_audio(args: argparse.Namespace) -> None:
    """Write [build.prebuilt] of uploaded audio packs into their source.toml."""
    from pipeline.build_audio import prebuilt_block  # noqa: PLC0415

    for source in _audio_sources(args):
        assert source.pack is not None
        archive = dist_dir() / f"{source.pack.id}.tar.zst"
        if not archive.exists():
            raise PipelineError(f"{archive}: not built")
        text = source.path.read_text(encoding="utf-8")
        marker = "[build.prebuilt]"
        if marker in text:
            text = text[: text.index(marker)].rstrip() + "\n"
        source.path.write_text(text + "\n" + prebuilt_block(archive, args.tag), encoding="utf-8")
        print(f"pinned  {source.pack.id}  {source.path.relative_to(repo_root())}")


def _add_audio_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    fetch_audio = sub.add_parser(
        "fetch-audio", help="download the Quran.com files of audio packs into .cache/"
    )
    fetch_audio.add_argument("--pack", action="append", help="only this audio pack (repeatable)")
    fetch_audio.add_argument(
        "--pin", action="store_true", help="list and pin sources without files.tsv"
    )
    fetch_audio.add_argument("--workers", type=int, default=8, help="parallel downloads")
    fetch_audio.set_defaults(func=cmd_fetch_audio)

    build_audio = sub.add_parser(
        "build-audio", help="encode, pack and check audio packs into dist/ (needs ffmpeg)"
    )
    build_audio.add_argument("--pack", action="append", help="only this audio pack (repeatable)")
    build_audio.add_argument("--fetch", action="store_true", help="fetch-audio first")
    build_audio.add_argument("--pin", action="store_true", help="with --fetch: pin new sources")
    build_audio.add_argument("--workers", type=int, default=8, help="parallel downloads")
    build_audio.add_argument(
        "--drop-upstream",
        action="store_true",
        help="delete each pack's downloaded files after it is built (saves disk)",
    )
    build_audio.add_argument(
        "--skip-built", action="store_true", help="skip packs already in dist/"
    )
    build_audio.set_defaults(func=cmd_build_audio)

    pin_audio = sub.add_parser(
        "pin-audio", help="pin uploaded audio packs in source.toml ([build.prebuilt])"
    )
    pin_audio.add_argument("--pack", action="append", help="only this audio pack (repeatable)")
    pin_audio.add_argument("--tag", required=True, help="the audio-* release holding the packs")
    pin_audio.set_defaults(func=cmd_pin_audio)


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
    manifest.add_argument(
        "--unpublished",
        action="store_true",
        help="also list built 'publish = false' packs (local testing with SIYAK_PACK_SOURCE)",
    )
    manifest.set_defaults(func=cmd_manifest)

    check = sub.add_parser("check-updates", help="list upstream changes since the pinned versions")
    check.add_argument("--source", action="append", help="only this source id (repeatable)")
    check.set_defaults(func=cmd_check_updates)

    evaluate = sub.add_parser(
        "eval-embeddings",
        help="compare embedding models on data/eval/semantic.toml (needs --group embed)",
    )
    evaluate.add_argument("--model", action="append", help="only this model key (repeatable)")
    evaluate.add_argument("--text", action="append", help="only this verse text (repeatable)")
    evaluate.add_argument(
        "--pack", action="append", help="evaluate this built vector pack instead (repeatable)"
    )
    _add_rate_limit(evaluate)
    evaluate.set_defaults(func=cmd_eval_embeddings)

    embeddings = sub.add_parser(
        "build-embeddings",
        help="build the model and vector packs into dist/ (needs --group embed)",
    )
    embeddings.add_argument("--pack", action="append", help="only this pack id (repeatable)")
    embeddings.add_argument(
        "--published", action="store_true", help="only packs with publish = true (releases)"
    )
    _add_rate_limit(embeddings)
    embeddings.set_defaults(func=cmd_build_embeddings)

    export = sub.add_parser(
        "export-vectors",
        help="write built verse vectors to dist/inputs/ for pinning (needs --group vectors)",
    )
    export.add_argument(
        "--pack", action="append", help="only this vector pack (default: the published ones)"
    )
    export.set_defaults(func=cmd_export_vectors)

    _add_audio_parsers(sub)

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
