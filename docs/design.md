# Design

The web app's visual direction. Screenshots of every screen: `docs/screenshots/ui/`.

## Direction: the mockup's, with a bigger sources panel (2026-10-19)

The user compared the design round's "paper and ink" (kept below as a dated section) with a mockup drawn separately in the planning chat, and chose the mockup's style with one change: a bigger sources panel. The mockup stays outside the repo (`_design-reference`, read only); nothing from it was copied in. Mapping: the mockup's Ask is Ask, its Filings look is Coverage (the look, not its data), and its landing look is the public demo page and, since 2026-10-25, the landing page itself.

- **A calm tool:** white cards with hairline borders on a pale green-grey page, and nothing else for decoration.
- **One green accent** for what you can act on or follow: buttons, links, the current tab, citations. Yellow is the highlighter: figures in the answer and the cited words in a filing. Amber is caution (the draft, "Not answered", offline), red is failure.
- **The answer reads like a filing:** serif text, figures under the highlighter, and each citation a small numbered box that leads to its source.
- **Sources sit beside the answer** in one panel, so each passage can be read next to the sentence that cites it.

## The change: a bigger sources panel

- From 64rem wide, Ask splits into two equal columns: the question and the answer on the left, the sources panel on the right. The panel takes about half the width; the mockup gives it a third.
- The panel fits the window from the first screen: it starts level with the question box, below the header and the title, and ends 16 px above the window's bottom edge. It sticks where it starts, so it stays put while the page scrolls. It scrolls on its own, so a long passage reads without moving the page, and scrolling it never scrolls the page (`overscroll-behavior: contain`).
- Its top is a sum in the CSS (`--panel-top`): the header's 56 px, main's 24 px top padding, the title's 27.5 px line and the 20 px gap below it. A change to any of them needs the sum changed too; the panel test fails when they drift apart.
- A citation still jumps to its source card: the URL, the card's outline and the focus work as before. After the jump, `components/quote-in-view.tsx` scrolls the panel, and only the panel, until the highlighted words are in view.
- On the demo page, each saved answer gets the same panel, as tall as its sources need up to the window's height.
- Below 64rem everything stacks as before: the question, the answer, then the sources.

## Mockup features, first set (2026-10-20)

Five of the mockup's features, each showing only what the app knows. What needs data the API does not give is left out and listed in `docs/todo.md`.

- **The answer's header strip** shows, on the right, what the browser timed from the question's send: "First words in 0.9 s · complete in 2.6 s · 2 sources". First words is the first draft text, and complete the checked answer. A reply with no draft text shows only "Complete in", and a refusal shows no count. Label grey at 13 px; on a phone it wraps below "Answer". Left out: the mockup's "every number checked", which needs the number check.
- **The footer strip** goes on below the usage line with two quiet outlined buttons, as in the mockup: "Copy answer with sources" (only when the answer cites a source) and "New question". On a phone they stack.
  - Copy puts the answer on the clipboard with its `[n]` markers, then "Sources" and one line per source: its name once its card has loaded, the quoted words and the filing's link. The status line says "Copied the answer with its sources.", or that copying failed.
  - New question stops a sources lookup still running, clears the answer and the question box, and puts the focus in it.
- **Coverage:** each filing ends with a green "Indexed" pill (the accent on the tint, fully round, 12 px semibold). The API lists indexed filings only, so that is the one status it knows. Left out: "Needs a look" and its reason, since the API exposes no per-filing ingest status.
- **The demo header** shows what the snapshot covers, "30 companies · 30 filings", in label grey before Sign in or Sign out, where the mockup's app header has its line. The pair wraps as one, so on a phone it takes the third row, at the right. Left out: the live header's line (the API gives no count) and the mockup's "latest" (nothing records that a filing is its company's latest).
- **Contrast:** the pill reaches 6.55:1 in light and 7.31:1 in dark, the timings and the coverage line 5.82:1 and 6.58:1, and the buttons' borders 3.42:1 and 4.19:1 against the footer strip.
- **Markup:** Ask's answer section gains a `div.result-head` (the h2 and `p.timings`) and a `div.actions` after `AnswerMain`; the demo header a `div.site-end` (the line and the button); each filing a `span.pill`. The reading and keyboard order is unchanged: the new buttons come after the answer's citations and before the sources panel, where they sit on screen, and the line and the pill take no focus.

## The landing page (2026-10-25)

The mockup's landing (`4-landing` in light, dark and phone; read only, nothing copied), built at `/` and public. Its figures come from the official eval report and the demo snapshot at build time, and nothing on it calls the API (memory.md, the landing page).

- **Bands:** the hero and the results on the pale page; "How an answer is made" and "Architecture" on full-width white bands with hairlines. Each band holds the page column.
- **Header:** the mark and the name, the section links and GitHub, then "Open the demo" as the green call to action. On a phone it takes three rows, as in the mockup.
- **Hero:** a green eyebrow in capitals, the title in the serif at 52 px (38 px on a phone), the lead, "Try the live demo" (green) and "Read sample answers, no sign-in" (outlined), and a note in label grey. From 64rem the saved answer sits beside the text; below, it follows it. The card has a soft shadow: the question in a header strip, the answer in the serif with its figure under the highlighter and its citation box, the source in a grey box (its name, the quoted value in mono, the check in green), and a caption.
- **How an answer is made:** four white cards, each step named in green mono; four across from 64rem, two from 40rem, one on a phone.
- **Evaluation results:** two lines on the run and on the live models, then Coverage's table look. Target and Result are right-aligned, and the result is bold. "Met" is the green pill and "Below target" the amber one. On a phone all four columns fit 390 px (cells 8 px apart, 13 px text), and "Below target" wraps to two lines.
- **Architecture:** six items, three across from 64rem and two from 40rem, then the stack as grey round chips.

Where the built page differs from the mockup, for the user to pick:

1. **Hero lead:** "30 companies' 10-K filings", without "latest" (nothing records it). "Every sentence cites a passage or an XBRL fact from the filing, every amount must match the source it cites" replaces "every number is checked against the filing's own XBRL data".
2. **Offline note:** 8 saved sample answers, the snapshot's count, not 15.
3. **Sample card:** the snapshot's n01 (Apple's fiscal 2025 revenue, citing one XBRL fact), not the mockup's net sales from fiscal 2023 to 2024 with a quoted Item 8 table.
   - The source line takes the app's own wording ("AAPL fact, Revenue from Contract with Customer, Excluding Assessed Tax, period ending 2025-09-27").
   - The amount reads as recorded ("416,161,000,000 USD", not "$416.2 billion").
   - The check line reads "Checked: the amount matches this XBRL fact", for "Numbers match the filing's XBRL facts".
   - A caption is added: "A saved answer from the evaluation's test run, as the demo shows it."
   - The citation box is the app's outlined one, filled on hover; the mockup's is filled.
4. **How an answer is made:**
   - Retrieve adds "Figures are looked up in the companies' XBRL facts first", and takes its 11,263 passages and top 50 from the report.
   - Answer says the draft streams first, marked as not yet checked, and the checked answer takes its place. The mockup said unsupported sentences go "before you see it".
   - Check has no fact count (no source). It says quotes must match word for word and amounts must match the fact or passage they cite; a failing draft is redone once; failing sentences are removed; with none left, the answer is a refusal.
5. **Results intro:** it names the run's models from the report (answers, routing, judge) and "questions from the golden set's test split". A second paragraph is added: the live site's models (Claude Haiku 5.5 first, then Gemini 3.5 Flash-Lite, then NVIDIA), and that the table measures the free models, not Claude.
6. **Table:**
   - Every ceiling target carries "≤" (false refusals, time to first token, full answer, cost); the mockup marks only false refusals.
   - The formats follow the report's rounding: "≤ 1 s" (mockup "1.0 s"), "≤ $0.0150" (mockup "$0.015"), faithfulness "97%" (mockup "97.0%"), recall "58.3%" (mockup "58%").
   - "Full answer latency, p95" replaces "End-to-end latency, p95": the report times it in the eval process, not through the web.
   - On a phone all four columns show; the mockup's phone shows only the Metric column, the rest cut off.
7. **Footnote:** it names the judge model, says the labels it was calibrated on are Claude's (kappa 0.84), not a human's, and adds that recall rests on 6 questions with AI-written passage labels, spot-checked by a non-expert.
8. **Architecture copy:**
   - Ingestion drops the "10 requests per second" (no source) and adds Redis and dead-letter queues.
   - Retrieval adds "fused by reciprocal rank".
   - Grounded generation says amounts must match "the fact or passage they cite", not "a reported XBRL fact".
   - CI says "Pull requests that change the answer pipeline", not "every pull request".
   - Tracing lists the stages it records: routing, facts, search and generation.
9. **Stack:** Redis and Claude added. At 1280 px the 14 chips take two lines.
10. **Column:** the content lines up with the header's page column, as on every other screen, and the fonts are the system's (Windows in the screenshots), as everywhere in the app.

## Layout

- **Header:** the mark and the name, then tabs with the current one underlined in green on the header's edge, then Sign out as a quiet outlined button. The demo's Sign in is a green button, like the mockup's landing call to action. On a phone the header takes three rows, as in the mockup: the name, the tabs, then the button.
- **Page column:** 82rem (1,312 px) with 64 px gutters, 32 px below 64rem and 24 px on a phone. The header lines up with it.
- **Ask:** as above. Before the first answer the right half stays empty, so the question box keeps its width when sources arrive.
- **Coverage**, in the mockup's Filings look: one table card with a grey head row, company names in semibold, tickers and CIKs in mono, and the pager as outlined buttons. On a phone the table scrolls inside its own region, as before.
- **Demo**, in the mockup's landing look: a serif title and lead, the saved questions as numbered cards on a full-width white band, then each saved question as a serif heading over its answer card and sources panel. The offline banner is the mockup's amber banner.
- **Sign-in and the error pages:** one white card under the mark.

## Type

System fonts only, as before: nothing downloads, nothing shifts while fonts load, and the CSP (`font-src 'self'`) needs no change.

- **Sans**, the system UI font, for the interface at a 15 px base. Page titles are 22 px bold, like the mockup's "Filings".
- **Serif** for reading: the answer at 20 px, passages at 17 px, the demo's title at 44 px (32 px on a phone) and its question headings at 28 px.
- **Mono** for identifiers and stacked figures: tickers, CIKs, accessions, a fact's value and token counts.
- Labels are 13 px. Table heads are 14 px in the sans, not small capitals.

## Color

| Role | Light | Dark |
| --- | --- | --- |
| Page | `#f4f5f2` | `#121514` |
| Cards, the header | `#ffffff` | `#191d1b` |
| Grey strips: table heads, card footers, the filing line | `#f0f2ee` | `#1f2422` |
| Text | `#1b1f1d` | `#e6e9e7` |
| Secondary text | `#444b47` | `#c3c9c5` |
| Labels and notes | `#5f6763` | `#9aa39e` |
| Hairlines | `#e2e5e0` | `#2b312e` |
| Field borders | `#7b847f` | `#7c8681` |
| Accent: buttons, links, the current tab, citations, focus | `#0f5f4b`, white text on it | `#5fcfae`, `#0b1f19` text on it |
| Tint: the demo banner, the card a citation jumped to | `#e3f1ec` | `#173129` |
| Highlighter: figures and cited words | `#fcefc0`, underline `#9a6a00` | `#4a3f14`, text `#fbefc6`, underline `#e0b54f` |
| Caution: the draft, "Not answered", warnings, offline | `#7a4d00` on `#fdf1dc` | `#f2c879` on `#2d2413` |
| Error | `#9b1c1c` on `#fbeceb` | `#ffb3ad` on `#36191a` |

Every text pair in use reaches 4.5:1. The lowest is 5.01:1, labels on the tinted card in light. Field borders, the focus ring and the quote's underline reach 3:1; the lowest is 3.52:1, the pager's border on the light page. The ratios use the WCAG formula, and axe passes on every screen in both themes. The mockup's light field borders would be about 1.5:1, so the fields keep a darker border.

## Spacing and shape

A 4 px base. Cards pad 16 to 20 px; cards have an 8 px radius and controls 6 px; pills are fully round.

## Answers, citations and sources

- **Citations:** the number in a small green outlined box, filled on hover. It stays inline in its sentence, which the 24 px target rule exempts, and its name stays "Source 1: AMZN 10-K FY2025, Item 1". The brackets stay in the page at zero size, so copied text still reads "[1]".
- **Figures:** amounts with a $, a %, "percent", a scale (thousand to trillion) or USD sit under the highlighter (`splitFigures` in `web/lib/answer.ts`). Years and dates do not.
- **The answer card:** a header strip ("Answer", and on Ask the timings), the answer, warnings in amber, notes in a dashed outline, and the token count and cost in a grey footer strip, which on Ask also holds Copy and New question.
- **The sources panel:** a header strip ("Sources"), then each source in turn, divided by hairlines:
  - "Source n" in green, then what the source is, and the filing line (company, section, filing date) in a grey box;
  - for a passage, its filing's period just under the heading, as in the mockup: "Fiscal year ended December 31, 2025", or "Quarter ended …" for a 10-Q, a long date in UTC, in secondary text at 14 px (8.96:1 on the card, 7.71:1 on the tinted card, light; 10.12:1 and 8.28:1, dark). It comes from the filing's `periodEnd`, SEC's period of report (2026-10-20). A fact card keeps its Period row, the value's own period, since a fact has no link to its filing;
  - a passage in serif behind a thin rule, the cited words under the highlighter with an underline, so colour is not the only cue;
  - a fact as label and value rows, the value in mono under the highlighter;
  - "Filing on sec.gov ↗" (the arrow has empty alt text, so no name changed) and "Back to the answer".
- **The card a citation jumped to:** a green tint and outline, as the mockup marks the open source.
- **States:** the draft is dashed with an amber "citations not checked yet" pill; a refusal shows an amber "Not answered" pill; errors sit in a red box; the status line keeps its green dot.

## What changed in the markup

- **Ask:** `div.ask` holds the column (`div.ask-main`: the form, the status line, an error, the draft and the answer) and the sources panel beside it. Sources is now the answer section's sibling instead of its child. The DOM order, so the reading and keyboard order, did not change: form, status, answer, sources. Neither did the headings: h1 Ask, h2 Answer, h3 Sources, h4 for each source.
- **`components/answer-view.tsx`:** `AnswerMain` and `SourceList`, which Ask places apart and the demo's `AnswerView` keeps together. Figures are wrapped in `span.figure`, and each citation's brackets in `span.bracket`.
- **`components/quote-in-view.tsx`:** the panel scroll after a citation's jump, on Ask and the demo. It renders nothing.
- **The demo:** its `main` has `className="demo"`.
- **One test changed:** the refusal test now looks for a "Sources" heading on the whole page, since Sources is no longer inside the answer section. A new test, in a 1024 by 360 window, checks that the panel's bottom edge sits 16 px above the window's on the first screen, that the panel is still on screen after a citation's jump, and that the citation brings its quote into view in it.

Styles still live only in `web/app/globals.css`, with no inline style, so the CSP did not change.

## Screenshots

`npm run build`, then `npm run screens` in `web/`, writes `docs/screenshots/ui/<screen>-<light|dark|phone>.png` against the mock API: light and dark at 1280 by 800, phone at 390 by 844 in light. Every screen passes axe before its screenshot. Each shot is a full page, except `offline`, which shows the top of the page: below its banner it is the demo page, shot in full as `demo`. The panel sticks, so a full-page shot shows it where it stands at the top of the page, its own scroll at the start. The screenshots come from Windows, so they show its fonts.

Screens: `sign-in`, `sign-in-error`, `landing`, `ask`, `ask-draft`, `ask-numeric`, `ask-textual`, `ask-comparison`, `ask-warnings`, `ask-refusal`, `ask-error`, `ask-sources-failed`, `coverage`, `demo`, `demo-coverage`, `offline`, `not-found`, `error`, `config-error`.

## Known limits

- When the answer column is shorter than the panel, the page can still scroll 48 px (main's bottom padding), and the panel moves up with it, so its bottom edge then sits 64 px above the window's. The end of a long page does the same.
- What the mockup shows and the app does not have (History, the pickers, "Read as", the number check, the Filings totals and detail panel, ingest jobs and more) is listed as candidates in `docs/todo.md`.
- Fonts differ from system to system, by choice: no web font is downloaded.
- From 641 px to about 690 px wide (measured with Windows fonts), the demo header's coverage line and its button wrap together below the tabs, so the header looks cramped there. Nothing overlaps.
- The screenshots' timings come from the mock API, which streams at once, so they read "First words in 0.0 s". The demo shows no timings, since the snapshot records none.

## Earlier direction: paper and ink (design round, 2026-10-19, merged as #15)

Replaced by the direction above the same day. Kept as it was written, with its headings one level down.

### Direction: paper and ink

Analysts come to FilingLens to read an answer and then check it against the filing. The design serves that reading and checking, and adds nothing else.

- The answer reads like a short research note.
- Every citation is a visible marker that leads to its source.
- Each source reads like an exhibit: what it is, where it comes from, then the filing's own words, with the cited words marked as a highlighter would mark paper.
- Calm and dense: no drop shadows, gradients, colored side stripes or other decoration. Color carries meaning, and never alone.

### Layout

- One page column, 72rem wide. The white header lines its content up with it.
- **Ask:** the question box, the status line, then the result. From 64rem wide, the result splits in two: the answer stays in view on the left while its sources scroll on the right, so each passage sits next to the sentence that cites it. Below 64rem everything stacks in reading order. The HTML order is the same either way, so keyboard and screen reader order did not change.
- **Demo:** the banner, the list of saved questions, then each question as its own section with the same answer and sources layout.
- **Coverage:** one white table. On a narrow screen it scrolls inside its own region, as before.
- **Sign-in and the error pages:** one narrow white card on the paper, under the lens mark.

### Type

System fonts only: nothing downloads, nothing shifts while fonts load, and the CSP (`font-src 'self'`) needs no change.

- **Serif** for what is read: the answer, the passages, page titles and the demo's questions (Iowan Old Style or Charter on a Mac; Sitka Text, Cambria or Georgia on Windows).
- **Sans**, the system UI font, for controls, labels and notes.
- **Mono** for identifiers: accession numbers, CIKs, request ids and token counts.
- Tabular figures where numbers stack: facts, tables and token counts.
- Small capitals with letter spacing name sections ("Answer", "Sources") and a fact's fields.
- Sizes: 12 to 15 px for labels and notes, 16 px body text, 19 px for the answer, 22 px for the demo's questions, 32 px for page titles (26 px on a phone).

### Color

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

### Spacing

A 4 px base: 4, 8, 12, 16, 20, 24, 32, 48 and 64 px. Cards pad 16 by 20 px, sections sit 20 to 32 px apart, and every corner has a 6 px radius.

### Answers, citations and sources

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

### What did not change

Every text, role, test id, link, focus order and behavior. The markup gained only wrappers and class names: the answer column (`answer-main`), "Source n" as its own span in the card heading (the heading's text is the same), the fact card's value and accession rows, the coverage table's ticker and CIK, the offline banner, and the Ask form and result. Styles live only in `web/app/globals.css`, with no inline style, so the CSP did not change.

### Known limits

- While pinned, an answer column taller than the window stays partly out of view; its end shows once its sources end. The longest saved answer (x02, with its warnings) fits an 800 px window.
- Fonts differ from system to system, by choice: no web font is downloaded.
