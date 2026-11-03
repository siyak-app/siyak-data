# morphology.qac: Quranic Arabic Corpus, morphology v0.4

| | |
|---|---|
| Publisher | Quranic Arabic Corpus, Kais Dukes, University of Leeds: <https://corpus.quran.com> |
| Version | 0.4 (May 2011); `quranic-corpus-morphology-0.4.txt`, 128,219 segments, 77,429 words, 6,236 verses |
| Based on | Tanzil Uthmani text 1.0.2 (its notice is part of the file header) |
| License | GNU General Public License, version not stated (GPL-3.0 text included as `LICENSE` / `qac/COPYING`), with QAC's terms of use |
| Used in | the `morphology.qac` pack (`morphology.qac.tar.zst`) |

## Obtaining the file

The download page (<https://corpus.quran.com/download/>) asks for an e-mail
address, so the zip is downloaded by hand and saved unchanged as
`.cache/morphology.qac/quranic-corpus-morphology-0.4.zip`. `fetch` checks its
sha256, then extracts the single text file from it and checks that sha256 too.
Builds in CI take the zip from the siyak-data release `sources-qac-0.4`
(a verbatim copy; see "Mirror").

The text file is byte-identical to the independent copy bundled with
QuranTree.jl (`data/quranic-corpus-morphology-0.4.txt`), checked on 2026-10-21.

## Terms of use and how we comply (spec §5.3.1)

| Term | Compliance |
|---|---|
| Verbatim copies only; "CHANGING IT IS NOT ALLOWED" | The pack contains the original file byte-for-byte (`qac/quranic-corpus-morphology-0.4.txt`, sha256 checked by `validate`). The SQLite tables are derived from it by format conversion only: no tag is added, removed or corrected |
| Source clearly indicated, with a link to corpus.quran.com | Pack `attribution` and `license_terms`; the app shows "Source: Quranic Arabic Corpus" with the link in the word card, Word panel, concordance, exports and About → Sources |
| Copyright notice included in copies and derived works | `NOTICE` = the file header verbatim (both the QAC and the Tanzil 1.0.2 notices, CRLF line endings kept), shipped as `qac/NOTICE` |
| GNU license | The GPL-3.0 text ships as `qac/COPYING`. QAC states no version; the GPL allows choosing any published version in that case |
| FAQ: non-commercial use; cite in research | Siyak is non-commercial; stated in `license_terms`; `citation` metadata for exports |

Errors in tags are never fixed in the pack; see `docs/qac-errata.md`.

## Alignment with Tanzil 1.1

QAC follows Tanzil 1.0.2; Siyak uses Tanzil 1.1. The differences are handled
by documented comparison rules (`docs/qac-alignment.md`), never by changing
either text.

## Mirror

```sh
gh release create sources-qac-0.4 --repo siyak-app/siyak-data --latest=false \
  --title "Source mirror: Quranic Arabic Corpus 0.4" \
  --notes "Verbatim copies (see sources/morphology/qac/README.md)." \
  .cache/morphology.qac/quranic-corpus-morphology-0.4.zip .cache/morphology.qac/COPYING
```
