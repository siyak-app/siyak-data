# audio.dussary: Yasser ad-Dussary

Verse-by-verse recitation by Yasser ad-Dussary (murattal, Hafs ʿan ʿĀṣim), as an audio pack
(`docs/pack-format.md` §4.10).

## Origin

| | |
|---|---|
| Publisher | EveryAyah, https://everyayah.com |
| Upstream | one mp3 per verse, `https://everyayah.com/data/Yasser_Ad-Dussary_128kbps/SSSAAA.mp3` (128 kbit/s) |
| Pins | `files.tsv` (name, sha256, url of every upstream file) |
| Processing | each verse re-encoded to mono MP3, 64 kbit/s, no tags |

Quran.com has this recitation only as one file per surah (chapter reciter 97). Its verse
timings do not fit all of those files (a surah file shorter than its timings, or timings out
of order), so the pack takes EveryAyah's verse files and cuts nothing.

Verse files do not include the basmala; the app plays `001001.mp3` (al-Fātiḥa 1:1) before
the first verse of every surah except al-Fātiḥa and at-Tawba.

## Rights

EveryAyah states no license for its recitation audio; the rights belong to the reciter and
the recording's producer. Whether the audio may be redistributed was not verified. The
project maintainer decided on 2026-11-07 to publish the pack with attribution, for personal
and non-commercial listening, and to remove it at the rights holder's request (app ADR
0014). `LICENSE` is shipped in the pack and shown on About → Sources.

## Rebuild

```sh
uv run siyak-data build-audio --pack audio.dussary --fetch --drop-upstream
```
