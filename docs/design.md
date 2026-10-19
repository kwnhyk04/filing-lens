# Design

The web app's visual direction (design round after step 9, 2026-10-19). Screenshots of every screen: `docs/screenshots/ui/`.

## Direction: paper and ink

Analysts come to FilingLens to read an answer and then check it against the filing. The design serves that reading and checking, and adds nothing else.

- The answer reads like a short research note.
- Every citation is a visible marker that leads to its source.
- Each source reads like an exhibit: what it is, where it comes from, then the filing's own words, with the cited words marked as a highlighter would mark paper.
- Calm and dense: no drop shadows, gradients, colored side stripes or other decoration. Color carries meaning, and never alone.

## Layout

- One page column, 72rem wide. The white header lines its content up with it.
- **Ask:** the question box, the status line, then the result. From 64rem wide, the result splits in two: the answer stays in view on the left while its sources scroll on the right, so each passage sits next to the sentence that cites it. Below 64rem everything stacks in reading order. The HTML order is the same either way, so keyboard and screen reader order did not change.
- **Demo:** the banner, the list of saved questions, then each question as its own section with the same answer and sources layout.
- **Coverage:** one white table. On a narrow screen it scrolls inside its own region, as before.
- **Sign-in and the error pages:** one narrow white card on the paper, under the lens mark.

## Type

System fonts only: nothing downloads, nothing shifts while fonts load, and the CSP (`font-src 'self'`) needs no change.

- **Serif** for what is read: the answer, the passages, page titles and the demo's questions (Iowan Old Style or Charter on a Mac; Sitka Text, Cambria or Georgia on Windows).
- **Sans**, the system UI font, for controls, labels and notes.
- **Mono** for identifiers: accession numbers, CIKs, request ids and token counts.
- Tabular figures where numbers stack: facts, tables and token counts.
- Small capitals with letter spacing name sections ("Answer", "Sources") and a fact's fields.
- Sizes: 12 to 15 px for labels and notes, 16 px body text, 19 px for the answer, 22 px for the demo's questions, 32 px for page titles (26 px on a phone).

## Color

One accent: blue means "you can follow this". Yellow means "the filing says this". Amber is caution, red is failure.

| Role | Light | Dark |
| --- | --- | --- |
| Paper, the page | `#f6f5f1` | `#111316` |
| Sheet: cards, the header | `#ffffff` | `#181b1f` |
| Ink, the text | `#1a1c20` | `#e8e6e1` |
| Secondary text | `#474c55` | `#b9bdc4` |
| Labels and notes | `#62676f` | `#9ba1aa` |
| Rules | `#dedad0` | `#2a2e34` |
| Field borders | `#737882` | `#858b94` |
| Accent: links, citations, buttons, focus | `#1e4d8c` | `#8db3ff` |
| Citation pill | `#e9eff8` | `#1b2638` |
| Highlighter, under the quote | `#ffe28a` | `#5b4b14`, text `#fff2c2` |
| Caution: warnings, the draft tag, offline | `#6a4500` on `#fbf2dc` | `#f1d18e` on `#2c2414` |
| Error | `#8f1f1a` on `#fbeceb` | `#ffb3ad` on `#36191a` |
| Demo banner | ink on `#edf2f8` | ink on `#172131` |

Every text pair in use reaches 4.5:1 (the lowest is 5.22:1, labels and notes on the light paper), and field borders and the focus ring reach 3:1 (the lowest is 4.06:1), by the WCAG formula. axe passes on every screen in both themes.

## Spacing

A 4 px base: 4, 8, 12, 16, 20, 24, 32, 48 and 64 px. Cards pad 16 by 20 px, sections sit 20 to 32 px apart, and every corner has a 6 px radius.

## Answers, citations and sources

- **Citations:** each `[n]` is a small blue pill in the sans face. Shape, face and weight set it apart from the serif text, so color is not the only cue. Its name stays "Source 1: AMZN 10-K FY2025, Item 1", and it stays inline in its sentence, which the 24 px target rule exempts.
- **Source cards:** "Source n" in small blue capitals, then what the source is; a line with the company, the section and the filing date; then the evidence.
  - A passage is set in a smaller, muted serif behind a thin rule. The cited words take full ink, the highlighter and an underline, so the eye lands on them first and the context stays readable.
  - A fact card reads like a ledger: field names in small capitals, the value large in tabular figures, the accession in mono.
  - The card a citation jumped to gets a blue outline.
- **States:**
  - The draft is dashed and muted, with an amber "citations not checked yet" pill, until the checked answer replaces it.
  - A refusal shows a grey "Not answered" pill.
  - Validation warnings sit in an amber box. A note about something left incomplete, such as a failed sources lookup, gets a dashed outline like the draft's.
  - Errors sit in a red box.
  - The status line shows a blue dot while it has something to say.
- **The lens mark:** a blue ring with a highlighter glint, drawn in CSS, before the name in the header and at the top of each card page. It adds no text, so no link's name changed.

## What did not change

Every text, role, test id, link, focus order and behavior. The markup gained only wrappers and class names: the answer column (`answer-main`), "Source n" as its own span in the card heading (the heading's text is the same), the fact card's value and accession rows, the coverage table's ticker and CIK, the offline banner, and the Ask form and result. Styles live only in `web/app/globals.css`, with no inline style, so the CSP did not change.

## Screenshots

`npm run build`, then `npm run screens` in `web/`, writes `docs/screenshots/ui/<screen>-<light|dark|phone>.png` against the mock API: light and dark at 1280 by 800, phone at 390 by 844 in light. Every screen passes axe before its screenshot. Each shot is a full page, except `offline`, which shows the top of the page: below its banner it is the demo page, shot in full as `demo`. The screenshots come from Windows, so they show its fonts.

Screens: `sign-in`, `sign-in-error`, `ask`, `ask-draft`, `ask-numeric`, `ask-textual`, `ask-comparison`, `ask-warnings`, `ask-refusal`, `ask-error`, `ask-sources-failed`, `coverage`, `demo`, `demo-coverage`, `offline`, `not-found`, `error`, `config-error`.

## Known limits

- While pinned, an answer column taller than the window stays partly out of view; its end shows once its sources end. The longest saved answer (x02, with its warnings) fits an 800 px window.
- Fonts differ from system to system, by choice: no web font is downloaded.
