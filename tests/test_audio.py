"""Audio packs (pack-format §4.10): layout, Quran.com addresses, cuts, pins and the
manifest's prebuilt entries. Encoding tests need ffmpeg and are skipped without it."""

import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from pipeline import build_audio, quran_com
from pipeline.archive import build_archive, extract_archive
from pipeline.build_audio import (
    Pin,
    chapter_cuts,
    check_audio_file,
    check_audio_pack,
    check_timings,
    encode_chapter,
    encode_verse,
    prebuilt,
    read_pins,
    verses,
    write_pins,
)
from pipeline.errors import PipelineError
from pipeline.install import (
    AUDIO_DB_MEMBER,
    AUDIO_LICENSE_MEMBER,
    AYAH_COUNTS,
    audio_member,
    audio_members,
    schema_supported,
)
from pipeline.manifest import build_manifest
from pipeline.schema import SCHEMA_VERSION, PackInfo, new_database, write_pack_info
from pipeline.sources import load_source

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")

SOURCE_TOML = """
[source]
id = "audio.test"
name = "Test recitation"
homepage = "https://quran.com"
license = "x"
attribution = "Recitation: Test"

[build]
quran_com = "verses"
recitation_id = 7
{prebuilt}

[pack]
id = "audio.test"
type = "audio"
lang = "ar"
title = {{ tr = "Test Kari", en = "Test Reciter" }}
author = "Test"
version = "1.0.0"
license = "x"
attribution = "Recitation: Test"
publish = true

[pack.meta]
reciter = {{ tr = "Test Kari", en = "Test Reciter" }}
style = "murattal"
"""


def _source(tmp_path: Path, prebuilt_block: str = "") -> Path:
    directory = tmp_path / "sources" / "audio" / "test"
    directory.mkdir(parents=True)
    path = directory / "source.toml"
    path.write_text(SOURCE_TOML.format(prebuilt=prebuilt_block), encoding="utf-8")
    return path


def test_layout_has_one_file_per_verse() -> None:
    assert sum(AYAH_COUNTS) == len(verses()) == 6236
    members = audio_members()
    assert len(members) == 6238
    assert {
        AUDIO_DB_MEMBER,
        AUDIO_LICENSE_MEMBER,
        "audio/002255.mp3",
        "audio/114006.mp3",
    } <= members
    assert audio_member(1, 1) == "audio/001001.mp3"
    assert "audio/114007.mp3" not in members


def test_files_only_packs_accept_older_schemas() -> None:
    assert schema_supported("audio", 1)
    assert schema_supported("model", SCHEMA_VERSION)
    assert not schema_supported("audio", SCHEMA_VERSION + 1)
    assert not schema_supported("translation", SCHEMA_VERSION - 1)
    assert schema_supported("translation", SCHEMA_VERSION)


def test_quran_com_addresses_become_https() -> None:
    assert (
        quran_com.absolute_url("Alafasy/mp3/001001.mp3")
        == "https://verses.quran.com/Alafasy/mp3/001001.mp3"
    )
    assert (
        quran_com.absolute_url("//mirrors.quranicaudio.com/everyayah/Husary_64kbps/002001.mp3")
        == "https://mirrors.quranicaudio.com/everyayah/Husary_64kbps/002001.mp3"
    )
    assert quran_com.absolute_url("http://x.example/a.mp3") == "https://x.example/a.mp3"
    assert quran_com.verse_key("2:255") == (2, 255)
    with pytest.raises(PipelineError):
        quran_com.verse_key("x")


def test_chapter_cuts_fall_in_the_pauses() -> None:
    timings = [(280, 3080), (3300, 9010), (9000, 15680), (16080, 22050)]
    # Before the first verse; the middle of each pause; an overlap cuts at the later start.
    assert chapter_cuts(timings) == [130, 3190, 9000, 15880]


def test_timings_must_cover_every_verse_in_order() -> None:
    timings = {v: (i * 10, i * 10 + 5) for i, v in enumerate(verses())}
    check_timings(timings, "t")
    missing = dict(timings)
    del missing[(2, 255)]
    with pytest.raises(PipelineError, match="miss"):
        check_timings(missing, "t")
    backwards = dict(timings)
    backwards[(2, 3)] = (0, 1)
    with pytest.raises(PipelineError, match="out of order"):
        check_timings(backwards, "t")


def test_pins_round_trip(tmp_path: Path) -> None:
    source = load_source(_source(tmp_path))
    pins = [Pin("002001.mp3", "b" * 64, "https://b"), Pin("001001.mp3", "a" * 64, "https://a")]
    write_pins(source, pins)
    assert [p.name for p in read_pins(source)] == ["001001.mp3", "002001.mp3"]


def test_prebuilt_needs_every_key_and_an_audio_tag(tmp_path: Path) -> None:
    good = (
        '[build.prebuilt]\ntag = "audio-2026.11.0"\nsize = 10\ninstalled_size = 20\nsha256 = "ab"\n'
    )
    assert prebuilt(load_source(_source(tmp_path / "a", good))) == {
        "tag": "audio-2026.11.0",
        "size": 10,
        "installed_size": 20,
        "sha256": "ab",
    }
    with pytest.raises(PipelineError, match="audio-"):
        prebuilt(load_source(_source(tmp_path / "b", good.replace("audio-", "data-"))))
    with pytest.raises(PipelineError, match="exactly"):
        prebuilt(load_source(_source(tmp_path / "c", good.replace("size = 10\n", ""))))


def test_manifest_lists_pinned_audio_packs_without_downloading(tmp_path: Path) -> None:
    pinned = (
        '[build.prebuilt]\ntag = "audio-2026.11.0"\nsize = 812\n'
        f'installed_size = 900\nsha256 = "{"c" * 64}"\n'
    )
    sources = [load_source(_source(tmp_path / "pinned", pinned))]
    manifest, warnings = build_manifest(sources, tmp_path / "dist", tag="data-2026.11.0")
    (entry,) = manifest["packs"]
    assert entry["url"].endswith("/download/audio-2026.11.0/audio.test.tar.zst")
    assert (entry["type"], entry["size"], entry["installed_size"]) == ("audio", 812, 900)
    assert entry["meta"]["style"] == "murattal"

    unpinned = [load_source(_source(tmp_path / "unpinned"))]
    manifest, warnings = build_manifest(unpinned, tmp_path / "dist", tag="data-2026.11.0")
    assert manifest["packs"] == []
    assert any("no [build.prebuilt]" in w for w in warnings)


def _sine(path: Path, seconds: float, channels: int = 2) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={seconds}", "-ac", str(channels), str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


@needs_ffmpeg
def test_encodes_mono_and_cuts_chapters(tmp_path: Path) -> None:
    src = _sine(tmp_path / "verse.mp3", 1.5)
    out = tmp_path / "out.mp3"
    encode_verse(src, out)
    assert check_audio_file(out) is None
    assert build_audio.probe(out)["channels"] == "1"

    chapter = _sine(tmp_path / "chapter.mp3", 6.0)
    parts = encode_chapter(chapter, [500, 2500, 4000], tmp_path / "parts")
    durations = [float(build_audio.probe(p)["duration"]) for p in parts]
    assert len(parts) == 3
    assert durations[0] == pytest.approx(2.0, abs=0.1)
    assert durations[2] == pytest.approx(2.0, abs=0.1)

    short = _sine(tmp_path / "short.mp3", 0.1, channels=1)
    assert check_audio_file(short) is not None


def test_gate_checks_an_audio_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Each file's own check (ffprobe) is tested above; here every verse is counted.
    probed: list[str] = []

    def fake_check(path: Path) -> str | None:
        probed.append(path.name)
        return "bad" if path.name == "002255.mp3" and len(probed) > 6236 else None

    monkeypatch.setattr(build_audio, "check_audio_file", fake_check)
    mp3 = tmp_path / "v.mp3"
    mp3.write_bytes(b"ID3")
    db = tmp_path / AUDIO_DB_MEMBER
    with closing(new_database(db)) as conn:
        write_pack_info(conn, PackInfo("audio.test", "audio", "1.0.0", SCHEMA_VERSION, "t", "s"))
        conn.commit()
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Recitation: Test\n", encoding="utf-8")
    members = [(AUDIO_DB_MEMBER, db), (AUDIO_LICENSE_MEMBER, license_file)]
    members += [(audio_member(s, a), mp3) for s, a in verses()]
    archive = build_archive(tmp_path, "audio.test", members, 0, level=1)
    assert check_audio_pack(archive, "audio.test", "1.0.0") == []
    assert len(probed) == 6236
    assert check_audio_pack(archive, "audio.test", "2.0.0") == [
        "pack_info is audio.test/audio 1.0.0",
        "bad",
    ]

    files = extract_archive(
        archive, tmp_path / "x", expected=set(audio_members()), max_size=1 << 30
    )
    with closing(sqlite3.connect(files[AUDIO_DB_MEMBER])) as conn:
        assert conn.execute("SELECT type FROM pack_info").fetchone() == ("audio",)

    incomplete = build_archive(tmp_path, "audio.short", members[:-1], 0, level=1)
    with pytest.raises(PipelineError, match="expected"):
        check_audio_pack(incomplete, "audio.test", "1.0.0")
