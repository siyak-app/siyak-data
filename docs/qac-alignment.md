# QAC ↔ Tanzil alignment

The morphology pack attaches QAC's segmentation to the Tanzil Uthmani text:
`words.text_ar` is Tanzil's text and `word_segments.text_ar` is QAC's form.
Spec §5.3.1 requires that the two agree for every verse. These rules define
"agree". They are implemented in `pipeline/align.py` and checked by the build
and by `validate`. The build writes the full report to
`dist/reports/qac-alignment.md` (and `.json`).

**No per-word exceptions.** A word that does not satisfy the rules fails the
build. Changing a rule needs maintainer review of the report.

## Rules

**A1: mark tokens belong to the previous word.** Tanzil writes pause marks
(U+06D6–06DC), the sajdah sign (U+06E9) and the rub-el-hizb sign (U+06DE) as
separate space-separated tokens; QAC does not count them as words. A token made
only of these characters is attached, with its space, to the preceding word:

```
رَيْبَ ۛ فِيهِ ۛ  →  words: "رَيْبَ ۛ", "فِيهِ ۛ"
```

Invariant: for every verse, `" ".join(words.text_ar)` equals
`verses.text_uthmani`. The reader can therefore render a verse word by word
without losing any mark. With the pinned text (Tanzil Uthmani 1.1) A1 attaches
4,379 mark tokens and yields 77,433 words.

**A2: one-to-one pairing.** For every verse, the Tanzil words (after A1)
pair one to one with the QAC words, except as allowed by M.

**M: merged tokens.** QAC follows Tanzil 1.0.2, which writes some word pairs as
one word that Tanzil 1.1 splits into two tokens. In a verse whose word counts
differ, two consecutive Tanzil tokens form one word if their concatenation,
without or with the space, matches the QAC word under A3. The word keeps the
Tanzil text with its space (`text_ar = "بَعْدَ مَا"`), so A1's invariant still
holds, and `position` follows QAC's word numbering, so
`surah:ayah:position:idx` is always the QAC location.

**A3: same word.** The QAC segments of a word, converted from Buckwalter and
joined, are compared with the Tanzil word (without the attached marks):

| Level | Meaning |
|---|---|
| `exact` | identical code points |
| `canonical` | identical after removing tatweel and putting combining marks in canonical (NFD) order |
| `edition` | identical after also applying the spelling differences between Tanzil 1.0.2 (QAC's base) and 1.1, to both sides: **E1** a hamza above carried by a tatweel (1.1, `لَـَٔايَـٰتٍ`) = a standalone hamza (1.0.2, `لَءَايَٰتٍ`); **E2** small high yeh U+06E7 = small yeh U+06E6 (QAC's table has no U+06E7); **E3** alif maksura + dagger alif = tatweel + dagger alif |
| `skeleton` | identical after the search normalization (docs/normalization.md): same letters, marks ignored |
| `mismatch` | anything else |

The gate accepts **`exact`, `canonical` and `edition`**, plus words merged by M
at those levels. `skeleton` and `mismatch` fail the build.

These rules were approved in the M1b review (2026-10-21) after the report below.

## Report (QAC 0.4 against Tanzil Uthmani 1.1)

| | Words |
|---|---|
| exact | 71,390 |
| canonical (tatweel, mark order) | 5,722 |
| edition: E1 hamza on tatweel | 277 |
| edition: E2 small high yeh | 38 |
| edition: E3 alif maksura + dagger alif (12:39, 12:41) | 2 |
| skeleton / mismatch | **0** |
| **QAC words aligned** | **77,429 of 77,429** |

Of the exact matches, four are merged by M:

| QAC location | Tanzil 1.1 | QAC |
|---|---|---|
| 2:181:3 | بَعْدَ مَا | بَعْدَمَا |
| 8:6:4 | بَعْدَ مَا | بَعْدَمَا |
| 13:37:8 | بَعْدَ مَا | بَعْدَمَا |
| 37:130:3 | إِلْ يَاسِينَ | إِلْ يَاسِينَ (one QAC word whose form contains a space) |

Every build writes the full per-word report to
`dist/reports/qac-alignment.md` and `.json`.
