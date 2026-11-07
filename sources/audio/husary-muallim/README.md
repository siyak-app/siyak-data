# audio.husary-muallim: Mahmoud Khalil al-Husary (Muallim)

Verse-by-verse recitation by Mahmoud Khalil al-Husary (muallim, Hafs ʿan ʿĀṣim), as an audio pack
(`docs/pack-format.md` §4.10).

## Origin

| | |
|---|---|
| Publisher | Quran.com (Quran.Foundation) |
| Quran.com id | recitation 12 |
| Upstream | one mp3 per verse (API v4 `/recitations/12/by_chapter`) |
| Pins | `files.tsv` (name, sha256, url of every upstream file) |
| Processing | each verse re-encoded to mono MP3, 64 kbit/s, no tags |

Verse files do not include the basmala; the app plays `001001.mp3` (al-Fātiḥa 1:1) before
the first verse of every surah except al-Fātiḥa and at-Tawba.

## Rights

Quran.com states no license for its recitation audio; the rights belong to the reciter
and the recording's producer. Whether the audio may be redistributed was not verified.
The project maintainer decided on 2026-11-07 to publish the pack with attribution, for
personal and non-commercial listening, and to remove it at the rights holder's request
(app ADR 0014). `LICENSE` is shipped in the pack and shown on About → Sources.

## Rebuild

```sh
uv run siyak-data build-audio --pack audio.husary-muallim --fetch --drop-upstream
```
