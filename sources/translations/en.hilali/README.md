# en.hilali: Hilali & Khan

| | |
|---|---|
| Translator | Muhammad Taqi-ud-Din al-Hilali and Muhammad Muhsin Khan |
| Digitized text | Tanzil Project, <https://tanzil.net/trans/en.hilali>, "Last Update: December 13, 2010" |
| License | Tanzil terms: non-commercial use. Rights in the translation not verified |
| Used in | Standalone pack `en.hilali.sqlite` |

## Terms

The file's header contains no license terms (see `NOTICE`). Tanzil's translations
page states:

> The translations provided at this page are for non-commercial purposes only.
> If used otherwise, you need to obtain necessary permission from the translator
> or the publisher.
>
> If you are using more than three of the following translations in a website or
> application, we require you to put a link back to this page to make sure that
> subsequent users have access to the latest updates.
>
> Redistributing the following list in another website is not allowed, unless
> direct permission is granted by the Tanzil Project.

| Term | Compliance |
|---|---|
| Non-commercial use | Siyak is non-commercial. Shown in the pack's `license_terms` |
| Link back when using more than three translations | The link is in the pack's `attribution` and `license_terms` |
| The list may not be redistributed on another website without permission | Not confirmed with Tanzil: see below |

## Publication decision

Three questions from `docs/adding-a-source.md` were not verified: who holds the
rights to this translation, which edition it is, and whether it may be
redistributed as a downloadable file inside an app. Tanzil's non-commercial term
cannot grant rights that Tanzil does not hold, and whether its "list" term covers
a set of packs on GitHub Releases is unclear. The project maintainer decided to
publish on this basis on 2026-11-03. If a rights holder or Tanzil objects, set
`publish = false` and make a new data release.

## Line breaks in the file

Seven lines of the file continue the previous verse instead of starting a new
`surah|ayah|text` line (verses 2:140, 3:21, 3:94, 4:149, 9:24 and 9:80, which has
two). Each starts with a space, in the middle of a sentence. `parse_translation`
appends them to the verse, so only the line break is lost and every other
character is kept.

## Format

`surah|ayah|text` per line, 6,236 verses, UTF-8; header lines start with `#`.
