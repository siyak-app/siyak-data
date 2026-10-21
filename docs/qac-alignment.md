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

**A2: same number of words.** For every verse, the number of Tanzil words
after A1 equals the number of QAC words.

**A3: same word.** The QAC segments of a word, converted from Buckwalter and
joined, are compared with the Tanzil word (without the attached marks):

| Level | Meaning |
|---|---|
| `exact` | identical code points |
| `canonical` | identical after removing tatweel and putting combining marks in canonical (NFD) order |
| `skeleton` | identical after the search normalization (docs/normalization.md): same letters, marks ignored |
| `mismatch` | anything else |

The gate accepts: **`exact`, `canonical`** (`ACCEPTED_LEVELS` in
`pipeline/align.py`; to be confirmed with the report of the real file).

## Report

_To be filled in from the first build with the pinned QAC v0.4 file: counts
per level, every verse with a different word count, and the proposed rules for
the remaining differences._
