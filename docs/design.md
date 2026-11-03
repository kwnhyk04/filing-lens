# Design

The web app's visual direction. Screenshots of every screen: `docs/screenshots/ui/`.

## Direction: the mockup's, with a bigger sources panel (2026-10-19)

The user compared the design round's "paper and ink" (kept below as a dated section) with a mockup drawn separately in the planning chat, and chose the mockup's style with one change: a bigger sources panel. The mockup stays outside the repo (`_design-reference`, read only); nothing from it was copied in. Mapping: the mockup's Ask is Ask, its Filings look is Coverage (the look, not its data), and its landing look is the public demo page and, since 2026-10-25, the landing page itself.

- **A calm tool:** white cards with hairline borders on a pale green-grey page, and nothing else for decoration.
- **One green accent** for what you can act on or follow: buttons, links, the current tab, citations. Yellow is the highlighter: figures in the answer and the cited words in a filing. Amber is caution (the draft, "Not answered", offline), red is failure.
- **The answer reads like a filing:** serif text, figures under the highlighter, and each citation a small numbered box that leads to its source.
- **Sources sit beside the answer** in one panel, so each passage can be read next to the sentence that cites it.

## Coverage's table and pager (2026-11-03, branch `fl-coverage-table`)

The user's brief: restyle Coverage with 21st.dev's table with numeric pagination (Origin UI, MIT), ported faithfully into FilingLens's CSS: its sizes, spacing, hover, focus and disabled states, its colours in the app's tokens in both modes, with no Tailwind, shadcn or TanStack. Every column, value and link stays. This supersedes the list-table and pager notes below for Coverage.

- **The table** (`components/coverage-table.tsx`, the `.data-*` rules in `app/globals.css`):
  - A frame with a 1 px `--rule` border and an 8 px radius on `--sheet`.
  - A plain head, 44 px tall, in `--ink-3` at weight 500.
  - Cells with 12 px padding, text at 14/20 px.
  - A rule between rows, none under the last; a row tints to half `--sunk` on hover (150 ms).
  - Company names at weight 500.
  - Fixed columns (38%, 9rem, the rest), so no page moves them.
  - The caption is visually hidden; it still names the table and its scroll region.
- **The pager:**
  - Left: "Page 1 of 3", 14 px in `--ink-3`, the numbers in `--ink`; a polite live region.
  - Middle: Previous, at most five page numbers with a gap mark (Lucide's ellipsis) for pages left out, then Next. Each is a 40 px square with a 6 px radius, 4 px apart. The current page, Previous and Next are outlined (`--field` on `--sheet`), the other pages plain. All tint to `--sunk` on hover, take a 2 px `--accent` ring 2 px out on focus, and fall to half opacity when disabled.
  - Right: "10 / page", the component's select trigger (40 px, 6 px radius, `--field` border, a chevron at half opacity) as the browser's own select, with 10, 20 and 50.
- **State:**
  - `?page=&size=` in the URL (`history.pushState`, which Next's router follows), kept by a refresh, Back and a shared link. The size is also kept in `localStorage` (`fl-coverage-size`, read and written inside try/catch).
  - A new size goes to the page that holds the first row on screen, and keeps that row where it was.
  - A page past the end shows the last; any other page or size falls back to 1 and 10.
- **Phones (from 40rem down):** each company is a card (from 45rem down, as before). The pager keeps "Page 2 of 3", Previous, Next and the size on one row; the page numbers hide.
- **Loading:** the header and a skeleton in the table's shape (the frame, the head and ten rows of bars, the pager's parts; cards on a phone) stream at once, and the companies follow when the API answers. The bars pulse unless reduced motion is asked.
- **Left out:** the component's row selection, sortable headers, status badge and credit line. Coverage has no sort or filter, so nothing goes back to page 1.
- **Accessibility:**
  - A real table, with column and row headers.
  - Real buttons named "Go to previous page", "Page 2" and "Go to next page", with `aria-current="page"` on the current one.
  - Previous and Next are `aria-disabled` at the ends, so focus never drops.

## Ask's stage lets go and comes to rest (2026-11-03, branch `fl-ask-release`)

The user's brief, from their test on production (Alphabet against Meta, asked as the second question in a row): the two pulled-in sources stayed attached to the membrane after the answer finished. About 1 s after the card has fully settled, the sources must let go, the membrane's bridges retract and the bubbles drift back into the orbit, so a new question starts from a clean orbit. Ask's Pause button goes, so the ambient drift must stop by itself within 5 s of the card settling, and within 5 s of the page load when idle (WCAG 2.2.2); motion plays only while a question is answered and during that short settle. Phones and reduced motion stay still; the landing hero keeps its own Pause. This supersedes the sections below where they differ.

- **The let-go** (the `FREE` beat in `components/bond.tsx`): a second after the card is in place (`ENTER_MS` after the last part starts, then `RELEASE_MS`), each held source flashes, its tendril draws back to where it left the card, and it floats home to its place in the orbit at its own pace (about 1.2 s), still labelled as the answer's source. The next question's leave lets go quickly of any source still held, as before; with none held it plays nothing. The labels turn back into filings when the next question is read.
- **Coming to rest:** the stage rests on the empty stage, once an answer is done and after an error. Its bubbles drift at full pace, then over a second slow to a stop `CALM_MS` (4.5 s) after the rest began: the page load for the empty stage, the last part's start for an answer (`calmPace` in `lib/stage.ts`). Then the eyes' blink and the bubbles' shape loop stop too (`data-calm` on the engine's stage), the membrane and the field hold, and nothing moves until the next question. A hidden tab or a stage scrolled away stops it sooner. Phones and reduced motion keep the calm stage.
- **No Pause on Ask:** the stage stops by itself, so the keyboard meets no control of its own. The landing hero keeps its Pause and its loop.
- **The field's time** runs only while the field moves, so a field that held still goes on from where it stopped. ShaderGradient's own clock ran on while no frame was drawn, so the field jumped ahead when it moved again, which the screenshots caught at the let-go.

## Ask's reveal, part by part (2026-11-03, branch `fl-ask-reveal`)

The user's brief, from their own test on production: the membrane must wrap every part of the card at every step and at the end, with no lag; the parts must enter one by one like the hero's, the membrane growing to cover each, about 0.3 s apart and all within 3 s; the cost with 4 decimals; the filing bubbles drifting the whole time, as the hero's. The timing before the answer stays. This supersedes the next section's pull and reveal rows and the live-stage notes below it where they differ.

- **The reveal** (`lib/stage.ts`'s `revealParts` and `revealTimes`, played by `components/ask.tsx`): Read as, each source, the filing tags, the answer's heading with its timings, each sentence of the answer, the check line, the numbers table, the warnings and the note when there are any, then the foot. After the pull (700 ms on a graphics card), the parts start 300 ms apart, closer when an answer has more than about seven, so the last is in place within 2.95 s of the data however long the answer (`REVEAL_MS`).
- **Each part grows the card in:** the card's height eases from where the last part left it to its new height in 350 ms (`ENTER_MS`, Web Animations, clipped), so a part shows as the card's edge passes it, and rises 8 px into place. A sentence waits hidden in its place in the answer's bubble and fades in on its turn, so the text never reflows.
- **The membrane holds the card as it is:** once gathered, its two heads and its body are drawn round the card's live box in every frame (`env.card` in `components/bond.tsx`), growing with it at once and easing in when it shrinks; with nothing moving it fits it at once. It never trails the card and never lets a part show past it.
- **The drift:** the filing bubbles drift with the hero's motion values whenever motion is allowed and the stage is in view and not paused. Between beats the stage idles: only the bubbles move, and the membrane and the field hold still, so the graphics card rests between answers.
- **The cost** reads as the evaluation's table does: `cost $0.0026`.

## Ask tells the hero's story, and the landing polish (2026-11-03, branch `fl-polish`)

The user's brief: re-sequence Ask's live answer to the landing hero's story, hide empty cards, centre How an answer is made, one comparison table for the evaluation, Architecture with its evidence, and sign-in and sign-out fixes. Their answers: the hero's layout (the field hides while answering and comes back under the card; New question brings it back at the top), no draft shown, the reveal may wait (about 2 s at most after the data). This supersedes the sections below where they differ.

- **The sequence** (page-driven in `components/ask.tsx`, schedule in `lib/stage.ts`; the engine follows):

  | Step | What moves | Lasts |
  | --- | --- | --- |
  | Leave (an answer on screen) | The card's parts wipe upward (`clip-path`, never a fade); the membrane lets go of its held sources, each flashing back to its place as a plain filing. | 450 ms |
  | Send | The field hides; the card with the bubble takes the top of the stage; the question flies there from the field (`element.animate`). | 450 ms |
  | Reading | The membrane covers the card: the bubble and "Reading the filings…"; the covered filings float, none lit. | until the answer and its sources are in |
  | Pull (graphics card) | Tendrils reach each cited filing left and right, 120 ms apart, and hold it against the card. | 800 ms |
  | Reveal | Read as, the passages and their filing chips, the answer with its timings, the check with the rest: 220 ms apart, each rising 8 px (`card-arrive`). | settled by 1.91 s |

- **Without motion** (phones, reduced motion, Pause, a stage out of view or a hidden tab) every part shows at once in the same order; a Recent click and the demo always do.
- **The card** takes the hero's order everywhere: bubble, Read as, passages and filing chips, answer, check, then the number check, notes and the foot.
- **Below the stage:** Recent questions and Sources only when they hold something; a lone card takes the row; Sources appears once the answer is whole.
- **Sign-in:** a "Back to home" link with Lucide's arrow-left in the mark's row; sign-out lands on the landing page with a pill notice over the headline.
- **Landing:** How an answer is made centred (heading, each number over its card's middle, one height, text left-aligned); one comparison table after FreightAudit's (each run's model and date under its name, the figure in bold with its badge), the details as small notes under it; Architecture after FreightAudit's "Engineering, with its evidence" (a claim a row under a hairline, what it means, its files in mono, one a line, each a 24 px target), the stack's chips under it.

## Ask, the live version of the landing hero (2026-11-03)

The brief: Ask as the live version of the landing hero, its answer card in the hero's place. The plan was approved with the user's answers (memory.md): no API change; the passage rows stay in the card under the check, the membrane pulling each cited source onto its row; the Sources card keeps the full passages; Recent questions about 60% and Sources about 40% below; only the cited filings pulled in; nothing claimed while it reads; the answer never waits for an animation.

- **The stage** (`section.stage`, styled in `app/ask/ask.css`): the hero still's field, a soft ground with a teal glow at the top left and a blue one at the bottom right, in a 32 px rounded box under the page's title. One 38rem column holds the question field, its help line, the four example chips while the stage is empty, the status line, then the card. The question shows once, in the card's bubble; the field clears on send.
- **The field:** a glass pill holding the textarea ("Ask about a company's 10-K...", 3 to 1,000 characters) and a round green arrow, named "Ask", that becomes a pill reading "Answering…" while it waits. Enter sends; Shift+Enter, and an input method's Enter, start a new line. The focus ring circles the whole pill.
- **The card:** the hero still's membrane drawn in CSS (32 px radius, a teal glow at the top left, a blue one at the bottom right, a soft green shadow) round the answer card's parts, in the hero's colours: the question's bubble, Read as, the reply under "Answer" and its timings, the check, the numbered passages and their filings, the number check (it fits the column from 64rem), warnings, notes, then the usage with Copy, Ask again and New question. As in the hero's panel, every word sits on a bubble or a row, so it keeps 4.5:1 on the membrane's glows: the reply's head, the notes and the foot take the rows' background. An error sits in the card under the question.
- **While it reads:** "Reading the filings…" under the card, and the coverage list's first 11 filings as quiet chips (`AMZN 10-K FY2025`), none of them claimed.
- **Below the stage:** Recent questions (about 60%) and Sources (about 40%), each a white card, top-aligned; below 64rem they stack, Sources first (by `order`; the DOM, and so the keyboard, keeps Recent first). Empty, they read "Questions you ask will appear here." and "Sources for your answer appear here."; after a refusal, "This answer cites no sources.". From 64rem Sources scrolls on its own, at most 40rem tall.
- **The moving stage** (`components/ask-live.tsx`, on the landing hero's engine in `components/bond.tsx`): on a desktop that allows motion and draws WebGL on a graphics card, after the load event, as the landing hero does; phones, reduced motion and software renderers keep the calm stage. It draws the field (ShaderGradient) and the membrane live, under the page's own content:
  1. Empty: the six organisms rest round the field and the covered filings float on both sides, still.
  2. Reading: the organisms roam among the floating filings.
  3. The checked answer in: they gather round the card, two heads at its top corners and one body under it, the others drawn in.
  4. The sources in: each cited source (at most 4) takes its own filing's place, lit and labelled with its item or value; a tendril reaches it, the membrane closes round it and carries what it says to its row, where a ring ripples off its number. Then the eyes blink and everything rests.
  - It moves only while the answer is read, while it waits for its sources and while the pulls play; otherwise it is still. A Pause button sits in the stage's corner, after the card in the DOM. The card never waits for it: each part shows the moment the stream or the sources lookup reports it, and the membrane catches up.
  - Where it may load (the gate's media query), the stage keeps 40rem of height and the card 12 px of room for the heads from the first paint, so nothing moves when the motion starts.
- **Measured:** `/ask`'s JavaScript before the load event went from 147.1 KB gzip (8 files) to 149.0 KB (9 files), on a desktop and a phone; after it, a desktop on a graphics card loads 314.1 KB more (the engine, then three.js), a phone nothing.

## Ask's answer card, the app's look and the How section (2026-11-03)

The user's brief: Ask in the landing hero's answer-card style; FreightAudit's app look in FilingLens's colours, header and theme switch; and the landing's "How an answer is made" after FreightAudit's How it works. FreightAudit is the same owner's project, read only; its structure is followed here and nothing there changed. The user's answers to the plan: build on what the stream already reports, with no API change; passages below the answer, in the order they arrive; only the cited filings round the card; the landing's theme switch in the app header.

- **What the stream reports, and so what the card shows:** the answer stream sends the draft in pieces (`delta`), the whole checked answer (`completed`: the reading, the citations with their quotes, the number checks) and a problem (`failed`). Routing and retrieval run before the first piece and are never reported. Then the web's sources lookup names each cited passage's filing and item. The card shows each part only when it arrives:
  1. On send: the question in a bubble on the right, and "Answering." in the status line. No step is named.
  2. The draft's first piece: the reply bubble on the left, dashed, under "Draft" and an amber "citations not checked yet" badge.
  3. The checked answer: "Read as" fills the line kept empty for it, so nothing moves; the checked answer takes the draft's place under "Answer" and its timings; the check line lands ("Checked: 416,161,000,000 matches source 1."; each amount with its source, then "every quote matches its passage word for word" when a passage is cited; none for a refusal).
  4. The sources lookup: the numbered passages move in below the check, together, since they were not found one by one. Each shows its filing and item ("AMZN 10-K FY2025, Item 1") or a fact's name, then its quote. The filings they come from light up as chips under them ("AAPL 10-K FY2025"; a fact's form follows its period, since FilingLens holds 10-Ks and 10-Qs only). A failed lookup keeps the quotes under "Source 1" and adds the note.
  5. An error: in the card, under the question, in the red box, with the demo link where it was before.
- **The rest of the card:** the number-check table, warnings, the reranker note, then a grey foot with the usage and Copy, Ask again and New question. The sources panel stays beside the card from 64rem, and each [n] still leads there.
- **Motion:** what arrives moves up 8 px into place over 0.45 s, and each filing chip glows once. Nothing fades, so text keeps its contrast while it moves (axe can run mid-way). Nothing moves under reduced motion, nor for a stored answer or the demo's saved ones, which show whole. Plain CSS: no canvas, WebGL or animation library in the app.
- **The demo:** each of its 8 saved answers in the same card, at rest, beside its sources. Its question stays the section's heading for screen readers and shows in the card's bubble.
- **Badges,** after FreightAudit's `ui.tsx`: a tinted pill with its word and a dot, never colour alone. Green `ok` for done (an indexed filing, a target met); amber `warn` for not yet or not answered (the draft, "Not answered", a target missed). The landing's results keep the word and tint without the dot, as FreightAudit's landing does, so each table still fits 390 px.
- **Buttons:** one set. Green for the page's one call to action (Ask, the demo's Sign in); `secondary`, quiet and outlined, for everything beside it; `small` in a row of them.
- **Lists,** after FreightAudit's list table: a rounded frame, a plain head, roomier rows that tint on hover, figures right-aligned. Below 45rem Coverage's rows become cards: the company, "CIK 320193", then its filings with their Indexed badges, and nothing scrolls sideways. The number-check table takes the same look and still scrolls in its own region on a phone. Paging is quiet buttons with Lucide's chevrons.
- **Header:** the landing's theme switch (System, Light, Dark) between the coverage line and Sign out, on Ask, Coverage and the demo, set by the server from the `fl-theme` cookie. It is one tab stop, its checked radio. On a phone it sits beside the name, so the header keeps three rows; the DOM, and so the keyboard's order, is the desktop's.
- **How an answer is made:** four cards, their numbers in circles above them joined by a line. Each card holds an icon in a tinted square (Lucide's route, search, message-square-text and shield-check), a title, one line and two or three points: the old four boxes' facts, shortened, with the passage count and the reranker's 50 from the report. Four a row from 64rem; two a row between 40rem and 64rem, with no line from the second to the third; stacked on a phone, with no line.
- **The hero's find beat:** a pulled source is tugged sideways only. The tug toward its point on the card (18% of the way) often went up or down into the next row, where its label crossed the neighbouring filing's (measured for x12, n01 and c02).

## Recent questions (2026-11-01)

The session part of the mockup's History: this sign-in's last 10 answered questions, kept in the API's Redis for 30 minutes each (memory.md, 2026-11-01).

- **The list:** under the answer card in Ask's column, "Recent questions" in secondary text over one quiet outlined button per question, newest first, each a full row with the question and, at the right, the time it was answered in muted text (`2:02 PM`, the browser's time zone). It leaves out the question on screen and hides itself when it is empty or cannot be loaded. On a phone each row is at least 44 px tall and a long question wraps.
- **A click** shows that question's stored answer at once, with its reading, number checks and sources, and asks nothing: the question fills the box, the status line says "Answer from earlier in this session, with 1 source.", and the focus moves to the answer's text.
- **An answer from earlier,** picked from the list or asked again in other letter case or spacing, says so in the answer's header strip, "From earlier in this session · 2:02 PM", where a new answer shows its timings. Its actions add "Ask again" between Copy and New question, which answers anew with a model call and replaces the stored one.
- **While an answer is on its way** the list's buttons are `aria-disabled` and do nothing, as the Ask button is.
- **Refusals and failed answers** are never listed; nor are answers given after the reranker timed out (degraded).
- Light and dark use the existing tokens (`--field`, `--sheet`, `--ink-3`), so every text pair keeps its measured contrast.

## Mockup features, second set (2026-10-25)

Five more of the mockup's Ask features, each from real data (memory.md, mockup features 2).

- **Layout:** from 64rem Ask's answer column takes about two thirds and the sources panel the rest (`minmax(0, 2fr) minmax(20rem, 1fr)`), as in the mockup. This reverses the half-width panel below; the panel still sticks, fits the window and scrolls on its own. The demo's saved answers take the same split.
- **Read as:** between the question box and the answer, "Read as" in secondary text and one quiet outlined chip each for the kind ("Number question", "Comparison", "Text question", "Out of scope"), the companies, the years ("Fiscal 2024 and 2025"), a quarter, and the figure ("Net income"). They come with the completed answer, from the API's `reading`; the demo shows each saved answer's.
- **Number check:** under the answer text, Coverage's table look with its title in the grey strip: "Numbers checked against XBRL data" when every row cites a fact, else "against their sources". Columns: Figure (a fact's label and period end, or a passage's source name), In the answer, Reported (a fact's value and unit, or the number "as quoted", in mono), Result ("Matches" in green). The answer's header adds "every number checked". On a phone the table scrolls in its own region, which takes the keyboard focus (axe's `scrollable-region-focusable`).
- **Coverage line:** the live header shows "30 companies · 30 filings" before Sign out, from the API's totals, as the demo header does from the snapshot.
- **Sample questions:** under the empty question box, "Try a question the filings can answer" and one quiet outlined button per saved answer that was answered (6). A click fills the box and focuses it; nothing is asked until you press Ask. They go while a draft or an answer shows and come back with New question.

Where the build differs from the mockup:

1. History, Filings, Ingest jobs, the company and fiscal-year pickers, the source pager and "How it was found" are left out (not in scope).
2. The page keeps its "Ask" title and "Your question" label; the mockup has neither and labels the box "Ask about a company's annual report".
3. The chips are the router's one reading: one figure per question (the mockup shows two), the kind as the router names it, and a refusal's chips too.
4. The table's Figure column names the fact's label and its period end, not "Total net sales, fiscal 2024": a fact's fiscal year is its filing's, so the period end is the honest date. Passage rows show the number as quoted, since a passage has no XBRL fact.
5. The title adapts ("against their sources" when a row cites a passage); the mockup always says "against XBRL data".
6. Sources stay as one scrolling panel of cards, not the mockup's compact list in the answer card with a one-source pager.
7. The header line counts filings ("30 filings"), not "latest 10-Ks": nothing records that a filing is a company's latest.
8. Sample questions are new; the mockup shows a filled question instead.

## The change: a bigger sources panel

Superseded on 2026-10-25 by the mockup's two-thirds split (above); the rest of this section still holds.

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

## Landing, round 1: header, hero and logo (2026-11-02)

The user's round 1; round 2 (the features and how it works) comes later, and those sections are unchanged.

- **Header**, after the header of 21st.dev's hero4, in FilingLens's colours: the mark and the name; the section links and GitHub in the middle; the theme toggle, Sign in and "Open the demo" (the green call to action, the demo as before) at the right. It sticks to the top, see-through over the hero, and turns paper with a hairline once the page scrolls. Below 64rem the links, the theme and Sign in fold into a menu that drops over the page (a 44 px button; Escape closes it and returns the focus); the name, "Open the demo" and the menu button keep one row.
- **Theme:** System, Light and Dark as three radios with icons, each radio covering its icon, so clicks and arrow keys are the browser's own. The `fl-theme` cookie keeps Light or Dark a year; the root layout writes it as `data-theme` on `<html>`, so the server renders the chosen theme and nothing flashes. Every colour token is a `light-dark()` pair. The toggle is in the landing header only; every page follows the cookie.
- **Hero**, after Prompt Bond (MIT; `docs/third-party.md`):
  - The headline in two voices: "Every answer." heavy in ink, then "Straight from the filing." light in teal, in the system's display face (Segoe UI Variable Display on Windows). On a desktop each letter grows heavier as the pointer nears, where the face is variable.
  - The scope: "Ask a question about a fixed set of 30 companies' 10-K SEC filings. FilingLens finds the passages and answers with citations you can check." The 30 comes from the snapshot; there is still no "latest" (nothing records it).
  - The story is the snapshot's x12 from golden v1's test run: the question, how the router read it, its two passages (LLY 10-K FY2025, Items 7 and 1A, each with its quote, clamped to two lines), the answer with its citation links, and the check ("56 percent matches source 2, and every quote matches its passage word for word"; a unit test holds each quote to its passage). The caption stays "A saved answer from golden v1's test run, as the demo shows it."
  - The still is that story at its end, in HTML and CSS: a membrane-like card with two heads, and the field as a CSS gradient of the shader's colours. The first paint, phones and reduced motion get it. On a desktop (64rem, a fine pointer, motion allowed, WebGL on a graphics card: no major-performance caveat and no software renderer such as SwiftShader, llvmpipe or Windows' basic driver, which keep the still), two frames after the load event and once idle, the moving story takes its place: the page types the question into a glass capsule, six organisms bond to it, the membrane grows into the panel, tendrils pull in the two passages from the filings floating round it (the snapshot's other 10-Ks, as form and year), the answer reveals line by line and a second look checks it. Then the ShaderGradient field fades in over the still one. Replay and Pause sit at the hero's bottom right; a hidden tab, a hero scrolled away or reduced motion stops it.
  - Colours: light, warm paper #FAF8F3 with soft grey-blue and a pale teal; dark, ink navy #0F1B2D with a muted teal glow from #2DD4BF. The headline's teal is #0D9488 in light (large text, 3.5:1) and #2DD4BF in dark (9.3:1). The panel's text sits on translucent paper or navy rows, so it keeps 4.5:1 over the membrane.
- **Mark:** variant #6 redrawn on one circle: two arcs (radius 12, ending 36° above the bar) and a bar broken where that circle would cross it, teal inside the lens and ink pills sticking out past it. One stroke width (4), round ends, one gap (3) between every two strokes (`web/lib/logo.ts`; its unit tests check the gaps and that every copy matches). Light: navy #0F1B2D with teal #0D9488 (3.5:1 on paper); dark: paper #FAF8F3 with #2DD4BF; one-colour: `currentColor`. Files in `docs/brand/`. It is in every header and above the sign-in and error cards (a CSS background, light or dark), the favicon (`app/icon.svg`, dark in a dark browser; it reads at 16 and 32 px) and the app icon (`app/apple-icon.tsx`, the dark mark on navy, 180 px).
- **Left out, for the user to pick:** the hero's two calls to action and its offline note (the header has Sign in and "Open the demo"); a `favicon.ico` (current browsers take the SVG); a web app manifest; a raster still image of the field (the still is CSS and weighs nothing); the toggle in the app's own headers.
- **Screens:** `npm run screens` runs with reduced motion, so the landing's shots show the still.

## Landing, round 2: the overview and four hero fixes (2026-11-02)

The user's round 2. The header is unchanged; the hero changed only as the user's four review fixes asked.

- **Overview** (`#overview`, right under the hero, on the paper band), after Hirael's feature-10 (MIT; `docs/third-party.md`), in FilingLens's tokens and markup:
  - Head: the serif headline "At a glance." (36 px on a phone, 48 px from 40rem, line height 1.04) and one line under it, "A sourced answer, tested numbers, and the newest feature." (the user's final copy, 2026-11-02; round 2 had a small "Overview" label over "Where FilingLens stands.").
  - One white sheet split by 1 px hairlines in `--rule`, with a 12 px corner: six columns from 64rem, otherwise full width, with the two figures side by side.
  - The answer (4 columns, 2 rows): x04 from golden v1's test run, "What are Amazon's reportable segments?", its answer in serif (24 px, 30 px from 40rem) with its citation boxes, and under it the source in place of the person: the citation's number in a grey circle, "AMZN 10-K FY2025, Item 1" (form, year and item) and "From golden v1's test run". No name, no quote from a person.
  - Two figures (2 columns each): "Filings indexed", 30 (the snapshot's filings, one per company); "Exact numbers", 100% (numeric exact match, 12 of 12 within 0.5%, the same in both official runs of 2026-10-31). Mono, 36 px, 48 px from 40rem. "Numeric accuracy", the results table's name, wrapped at 390 px and put its value out of line with the other figure.
  - Recent questions (4 columns): "New in Ask", what the feature does in two sentences, and "Read the pull request" (#42 on GitHub), Ask's quiet outlined button with Lucide's arrow. Ask needs the site's password and the demo has no Recent questions, so the pull request is what any visitor can open.
  - What it does (2 columns): Ask, Cite and Check, one line each.
- **How it works** (three steps: Ask, Find the passages, Answer with citations): not built. The hero's subtitle says that flow in those words, its story shows it (the question, the passages with form, year and item, the answer with its citations, the check), and "How an answer is made" explains it in more depth below.
- **Hero fixes:**
  - Subtitle, the user's words: "Ask about the 10-K filings of 30 large US companies. FilingLens finds the passages and answers with citations you can check." The 30 still comes from the snapshot.
  - "Open the demo" (`/demo`, as in the header) under the subtitle, larger than the header's button, with the offline note under it: "When the live backend is offline, the site serves 8 saved sample answers." The landing calls no API, so the note is always there, whether the backend is up or not.
  - The still's two heads (Prompt Bond's two organisms, drawn in CSS at the card's top corners) are gone. The moving story's membrane keeps its eyes, which are part of Prompt Bond's engine.

## Landing, the hero's loop (2026-11-02)

The user's change: the moving story played once (about 20 s) and stopped until Replay; it now tells three saved answers in turn. The still, phones, reduced motion and software WebGL are as before.

- **The answers** (`LOOP` in `web/lib/story.ts`), all from the demo snapshot, no company twice: x12 first (Eli Lilly's growth drivers, two passages: the still's), then n01 (Apple's revenue in fiscal 2025, one XBRL fact) and c02 (Alphabet's revenue against Meta's, two facts from two filings). Each is answered, carries no warning and is 300 characters or less. Left out: x04 (Amazon's reportable segments, one passage; in the first build, then dropped by the user, since the overview just below the hero shows it), x02 (624 characters, written twice and cut by a sentence), c12 (four citations, facts and table rows mixed), o02 and t01 (refused).
- **Facts in the story:** a fact's row is its citation name and its value as published, without quote marks; round the panel it floats as "Fact" with its value and filing, under Lucide's hash. The caption counts what is cited ("One fact from AAPL 10-K FY2025 holds the answer."; c02's names both filings), and the check line names only the amounts when no passage is cited ("Checked: 416,161,000,000 matches source 1.").
- **The loop:** each answer plays as before (the question typed into the capsule, the membrane, the sources pulled in, the answer, the check), holds 7 s, then fades out over 0.6 s while the next fades in; after c02 comes x12 again. The hold and the fades run on the story's own clock, which stops whenever the motion stops, so a paused, hovered, hidden or scrolled-away story never moves on.
- **Pauses:** the pointer on the card, or keyboard focus inside it, pauses everything as Pause does, and leaving resumes. The caption and its controls do not count, so Replay and Pause stay usable. Replay tells the current answer again. A hidden tab, a hero scrolled away (IntersectionObserver) or reduced motion still stop it, and neither the membrane nor the field draws then.
- **The card** keeps the still's height (462 px at 1440 px wide), so nothing below the hero moves; a shorter answer's panel sits in the card's middle, round the capsule's line.
- **Accessibility:** the caption and its controls stay while the answers change, so focus on Replay or Pause stays put (before, Replay rebuilt them and focus fell back to the page). The cue is not announced while the loop turns (`aria-live="off"`, as in WAI-ARIA's carousel pattern), and is announced once it is paused.

## Layout

- **Header:** the mark and the name, then tabs with the current one underlined in green on the header's edge, then the coverage line, the theme switch (since 2026-11-03) and Sign out as a quiet outlined button. The demo's Sign in is a green button, like the mockup's landing call to action. On a phone the header takes three rows, as in the mockup: the name with the theme switch, the tabs, then the line and the button.
- **Page column:** 82rem (1,312 px) with 64 px gutters, 32 px below 64rem and 24 px on a phone. The header lines up with it.
- **Ask:** since 2026-11-03 the stage, then Recent questions and Sources below it (above).
- **Coverage**, in the app's list look since 2026-11-03: one rounded table with a plain head row, company names in semibold, tickers and CIKs in mono, and the pager as quiet buttons. On a phone each company is a card.
- **Demo**, in the mockup's landing look: a serif title and lead, the saved questions as numbered cards on a full-width white band, then each saved answer in Ask's card beside its sources panel (since 2026-11-03). The offline banner is the mockup's amber banner.
- **Sign-in and the error pages:** one white card under the mark.

## Type

System fonts only, as before: nothing downloads, nothing shifts while fonts load, and the CSP (`font-src 'self'`) needs no change.

- **Sans**, the system UI font, for the interface at a 15 px base. Page titles are 22 px bold, like the mockup's "Filings".
- **Serif** for reading: the answer at 20 px, passages at 17 px, and the demo's title at 44 px (32 px on a phone).
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

A 4 px base. Cards pad 16 to 20 px; cards have an 8 px radius (the demo's answer card 16 px; Ask's stage and its card 32 px, 24 px on a phone, as the hero's still) and controls 6 px; badges are fully round.

## Answers, citations and sources

- **Citations:** the number in a small green outlined box, filled on hover. It stays inline in its sentence, which the 24 px target rule exempts, and its name stays "Source 1: AMZN 10-K FY2025, Item 1". The brackets stay in the page at zero size, so copied text still reads "[1]".
- **Figures:** amounts with a $, a %, "percent", a scale (thousand to trillion) or USD sit under the highlighter (`splitFigures` in `web/lib/answer.ts`). Years and dates do not.
- **The answer card:** since 2026-11-03 the hero's card, as described at the top: the question, Read as, the reply under "Answer" and its timings, the check, the passages and their filings, then warnings in amber, notes in a dashed outline, and the token count and cost in a grey foot, which on Ask also holds Copy and New question.
- **The sources panel:** a header strip ("Sources"), then each source in turn, divided by hairlines:
  - "Source n" in green, then what the source is, and the filing line (company, section, filing date) in a grey box;
  - for a passage, its filing's period just under the heading, as in the mockup: "Fiscal year ended December 31, 2025", or "Quarter ended …" for a 10-Q, a long date in UTC, in secondary text at 14 px (8.96:1 on the card, 7.71:1 on the tinted card, light; 10.12:1 and 8.28:1, dark). It comes from the filing's `periodEnd`, SEC's period of report (2026-10-20). A fact card keeps its Period row, the value's own period, since a fact has no link to its filing;
  - a passage in serif behind a thin rule, the cited words under the highlighter with an underline, so colour is not the only cue;
  - a fact as label and value rows, the value in mono under the highlighter;
  - a calculation (2026-10-27) as "Source 3: Calculated by FilingLens from sources 1 and 2", a grey box linking its two sources ("the answer model did none of this arithmetic"), then its lines in sans at 15 px, figures under the highlighter, not set like a filing's quoted words;
  - "Filing on sec.gov ↗" (the arrow has empty alt text, so no name changed) and "Back to the answer".
- **The card a citation jumped to:** a green tint and outline, as the mockup marks the open source.
- **States:** the draft is dashed with an amber "citations not checked yet" badge; a refusal shows an amber "Not answered" badge; errors sit in a red box in the card, under the question; the status line keeps its green dot.

## What changed in the markup

- **Ask:** `div.ask` holds the column (`div.ask-main`: the form, the status line, an error, the draft and the answer) and the sources panel beside it. Sources is now the answer section's sibling instead of its child. The DOM order, so the reading and keyboard order, did not change: form, status, answer, sources. Neither did the headings: h1 Ask, h2 Answer, h3 Sources, h4 for each source.
- **`components/answer-view.tsx`:** `AnswerMain` and `SourceList`, which Ask places apart and the demo's `AnswerView` keeps together. Figures are wrapped in `span.figure`, and each citation's brackets in `span.bracket`.
- **`components/quote-in-view.tsx`:** the panel scroll after a citation's jump, on Ask and the demo. It renders nothing.
- **The demo:** its `main` has `className="demo"`.
- **One test changed:** the refusal test now looks for a "Sources" heading on the whole page, since Sources is no longer inside the answer section. A new test, in a 1024 by 360 window, checks that the panel's bottom edge sits 16 px above the window's on the first screen, that the panel is still on screen after a citation's jump, and that the citation brings its quote into view in it.

Styles still live only in `web/app/globals.css`, with no inline style, so the CSP did not change.

## Screenshots

`npm run build`, then `npm run screens` in `web/`, writes `docs/screenshots/ui/<screen>-<light|dark|phone>.png` against the mock API: light and dark at 1280 by 800, phone at 390 by 844 in light. Every screen passes axe before its screenshot. `SCREENS_DIR` writes the shots elsewhere, and `SCREENS_WIDTHS` (such as `1280,1440,1920,390`) shoots each width in light and dark instead, as `<screen>-<width>-<theme>.png`, on one worker: the sign-in error is then shot eight times, and locally every sign-in shares one limiter bucket, so each shot first signs in to empty it. Each shot is a full page, except `offline`, which shows the top of the page: below its banner it is the demo page, shot in full as `demo`. The demo's panel sticks, so a full-page shot shows it where it stands at the top of the page, its own scroll at the start; Ask's Sources card shows the start of its own scroll. `SCREENS_MOTION=1` (with `E2E_CHANNEL=msedge`, on a graphics card) shoots the desktop widths with motion allowed: each Ask screen then waits for the moving stage, and for its pulls to play. The screenshots come from Windows, so they show its fonts.

Screens: `sign-in`, `sign-in-error`, `landing`, `ask`, `ask-draft`, `ask-numeric`, `ask-textual`, `ask-comparison`, `ask-calculation` (after the [3] marker's jump, so the panel shows the calculation card), `ask-warnings`, `ask-recent` (x04's answer, n01 in the list), `ask-stored` (n01 picked from the list), `ask-refusal`, `ask-error`, `ask-sources-failed`, `coverage`, `demo`, `demo-coverage`, `offline`, `not-found`, `error`, `config-error`.

## Known limits

- On a desktop with a graphics card, a question sent within about a second of the page load can see its draft a moment late (290 ms, measured with the mock's quick draft) while the moving stage starts up: its WebGL, then the field's three.js.
- Resolved on 2026-11-03 (`fl-polish`): a new question no longer drops the answer at once; the card wipes away and the membrane lets go of its sources first. Before, the stage went back to rest at once while the card changed.
- A desktop whose WebGL is drawn in software keeps the calm stage, at the moving stage's 40rem height, with room below the examples.
- What the mockup shows and the app does not have (History, the pickers, "Read as", the number check, the Filings totals and detail panel, ingest jobs and more) is listed as candidates in `docs/todo.md`.
- Fonts differ from system to system, by choice: no web font is downloaded.
- From 641 px to about 690 px wide (measured with Windows fonts), the demo header's coverage line and its button wrap together below the tabs, so the header looks cramped there. Nothing overlaps.
- The screenshots' timings come from the mock API, which streams at once, so they read "First words in 0.0 s". The demo shows no timings, since the snapshot records none.
- Recent questions load in the browser after the page, so the list appears a moment after Ask opens, and its times are the browser's clock time with no date: a sign-in lasts 8 hours at most. `ask-recent` and `ask-stored` show the time of their run.

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
