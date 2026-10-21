# Notes for Quranpedia.net

Issues found in the Quranpedia.net data dumps while building Siyak's tafsir
packs (dump 2026-10-20). Siyak never corrects the text; where the pipeline
handles an issue (see `docs/pack-format.md` §4.6) the note says how. Each note
is meant to be forwarded to quranpedia.help@gmail.com; the "Sent" line records
when it was.

## 1. Book 301 (روح المعاني): author in the book metadata

`books.json`, entry 301, gives the author as أبو المعالي محمود شكري بن عبد الله
بن محمد بن أبي الثناء الألوسي, i.e. Maḥmūd Shukrī al-Ālūsī (d. 1342/1924), the
grandson. *Rūḥ al-Maʿānī* is by Shihāb al-Dīn Abū al-Thanāʾ Maḥmūd ibn ʿAbd
Allāh al-Ālūsī (d. 1270/1854); the edition (Dār al-Kutub al-ʿIlmiyya 1415, ed.
ʿAlī ʿAbd al-Bārī ʿAṭiyya) is of his work. Siyak credits the correct author.

- Sent: not yet

## 2. Book 272 (تفسير الجلالين): page residues in the text

692 content items consist only of a page-header residue such as `١ -` or
`١٥ -` (first ones: 10:13 page 268, 10:18 page 269, 10:22 page 270), and 4,571
items end with such a residue after a line break (e.g. 2:153, page 31:
`…بِالْعَوْنِ<br />\r١٥ -`). They look like running heads of the printed page,
not part of the commentary. The entry for 1:1 is missing. Siyak keeps the text
as published (M1c decision K5) and lists the counts in its coverage report.

- Sent: not yet

## 3. Edition matter filed under verses

Editors' and publishers' introductions, studies, manuscript plates, indexes
and printer colophons are attached to verses, usually the last verse of the
book, and several authors' introductions are attached to the last verse
instead of the first. Siyak leaves out the edition matter and moves the
author's introduction to 1:1 (rules in each `sources/tafsir/ar.*/source.toml`).

| Book | Verse(s) | Pages | Content |
|---|---|---|---|
| 4 الطبري | 114:6 | vol. 0, pp. 5–20; vol. 1, pp. 3–113 | editor's introduction (Maḥmūd Shākir); the author's introduction |
| 136 ابن كثير | 114:6 | vol. 0, pp. 7–75; vol. 1, pp. 5–100 | editor's introduction, study, manuscripts; the author's introduction |
| 2 البغوي | 114:1–6 | vol. 1, pp. 5–32; pp. 33–47 | editors' introduction, manuscripts; the author's introduction |
| 319 البيضاوي | 114:1–6 | vol. 1, pp. 5–20, 23; vol. 5, pp. 353–356 | editor's introduction; author's preface; table of contents |
| 322 البحر المحيط | 114:1–6 | vol. 1, pp. 3–7; pp. 9–26 | publisher's introduction; author's preface |
| 350 ابن عطية | 114:1–6 and volume ends | vol. 1, pp. 3–29, 33–59; tables of contents at the end of vols. 1–5; vol. 6 | editor's introduction; author's introduction; indexes |
| 343 الشوكاني | 114:1–6, 4:176, 44:38 | vol. 1, pp. 5–19, 629–632; vol. 2, p. 4; vol. 4, pp. 665–667; vol. 5, pp. 647–650; vol. 6 | editor's introduction; author's introduction; indexes |
| 468 الماتريدي | 3:200 | vol. 1, pp. 3–349 | editor's study (346 pages) and the author's introduction |
| 26 النسفي | 33:63; 114:6 | vol. 1, pp. 23–25; vol. 3, p. 701 | the author's preface; printer's closing line |
| 352 الرازي | 114:6 | vol. 32, pp. 379–380 | printer's colophon (خاتمة الطبع) |
| 273 الدر المنثور | 114:6 | vol. 1, pp. 9–19 | the author's introduction |
| 301 روح المعاني | 114:1 | vol. 1, pp. 3–35 | the author's preface and introduction |
| 346 الكشاف | 114:6 | part "المقدمة", pp. 1–4 | the author's introduction |

Also: book 343 files the opening of al-Māʾida (vol. 2, p. 5) under 4:176.

- Sent: not yet

## 4. Commentary filed under the wrong surah

- Book 4 (الطبري): the opening pages of the commentary on al-Aḥqāf (vol. 22,
  pp. 89, 92, 93: "تفسير سورة الأحقاف") are attached to every verse of Ghāfir,
  40:1–85, in addition to Ghāfir's own commentary. In Siyak's pack this makes
  40:1–85 a single passage.
- Book 468 (الماتريدي): commentary on al-Qaṣaṣ (vol. 8, pp. 146–161, starting
  "سُورَةُ الْقَصَصِ") is attached to verses of al-Naml (27:1–24).

- Sent: not yet

## 5. Structure of the re-keyed books (136, 343, 468, 273, 37)

- The `ayahs` field of a content item holds the verse number within the surah
  instead of the global verse id in many items (e.g. book 136, 10:2 has
  `"ayahs": "2"`), so it cannot be used to find verse groups.
- Items without a page (page 0 or missing) repeat, from a second digital
  edition, text that is already present with page numbers, and the labels
  "نص مكرر لاشتراكه مع الآية N" and "جزء ذو علاقة من تفسير الآية السابقة" introduce
  copies of other verses' text. Siyak stores such a copy once when it can
  verify it, and keeps it (label included) otherwise.

- Sent: not yet

## 6. Missing pages

- Book 336 (روح البيان): the entry for 1:1 starts mid-sentence on vol. 1, p. 6
  ("بالأكل والشرب…"); pp. 1–5 (the author's preface) are not in the dump.
- Book 37 (إرشاد العقل السليم): vol. 1 starts at p. 8; the author's preface
  (pp. 1–7) is not in the dump.

- Sent: not yet
