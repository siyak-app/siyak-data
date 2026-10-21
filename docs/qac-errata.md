# QAC errata

Known issues in the Quranic Arabic Corpus morphology (v0.4) reported by Siyak
users and contributors.

**The morphology pack is never changed by this list.** QAC's terms allow only
verbatim distribution of its data (spec §5.3.1), and Siyak does not correct
tags. The app may show "There is a known note for this tag" on a listed word;
the note comes from this file. Where possible, entries are forwarded to the
QAC maintainers.

Report an issue with the "QAC tag error" issue form. A maintainer adds the
entry here after review.

## Entry format

```
### <surah>:<ayah>:<word>:<segment>  <the segment in Arabic>

- QAC tag: <the tag/feature as in the file, e.g. "N|ACC">
- Note: <what seems wrong and why, in English>
- References: <grammar works, tafsir, i'rab sources>
- Reported: <issue link>, <YYYY-MM-DD>
- Forwarded to QAC: <yes/no, date>
```

## Entries

Entries marked *candidate* were noted by a maintainer during review and have
not been forwarded yet. Notes describe the QAC data only; the pack keeps it
exactly as published.

### 2:153:4:1  ٱسْتَعِينُ (candidate)

- QAC tag: `STEM|POS:V|IMPV|(X)|LEM:{sotaEiynu|ROOT:Ewn|2MP`
- Note: The lemma is given as `{sotaEiynu` (ٱسْتَعِينُ), which is the
  imperative/imperfect stem form rather than the dictionary form of the
  form X verb (the perfect, اسْتَعَانَ). The same lemma is used at 1:5:4,
  2:45:1 and 7:128:4, so the question concerns QAC's lemma convention for this
  verb, not this word alone.
- References: —
- Reported: M1b acceptance review (no issue), 2026-10-21
- Forwarded to QAC: no

### 112:2:2:2  صَّمَدُ (candidate)

- QAC tag: `STEM|POS:N|LEM:S~amad|ROOT:Smd|MS|NOM`
- Note: The lemma `S~amad` (صَّمَد) carries a shadda on its first letter.
  That shadda belongs to the assimilated definite article (ٱلصَّمَدُ, with the
  sun letter ص) and is not part of the lemma, whose expected form is صَمَد
  (`Samad`). This is the only occurrence of the lemma in the file.
- References: —
- Reported: M1b acceptance review (no issue), 2026-10-21
- Forwarded to QAC: no
