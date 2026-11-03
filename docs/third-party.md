# Third-party code and assets

Code and designs FilingLens's web app takes from others, beyond what its npm packages carry themselves.

| What | Where | From | Licence |
| --- | --- | --- | --- |
| Prompt Bond, the hero's moving story and, since 2026-11-03, Ask's moving stage: the membrane's shader and renderer, the organisms' steering, the layout and scatter, the beat timelines and the frame loop, adapted to FilingLens's saved answers, told in turn, and to Ask's live answer (a gather beat added) | `web/components/bond.tsx`, `web/components/bond.css` (the engine); `web/components/hero-live.tsx`, `web/components/hero-live.css` (the landing's); `web/components/ask-live.tsx` (Ask's) | Sanjay Kumar (Cojeev), from the 000h library, via 21st.dev: https://21st.dev/@luv-jeri_c92deb60/components/prompt-bond | MIT |
| Feature 10, the landing's overview: a serif head, then one sheet split by hairlines into a quote, two figures, the latest feature and three jobs; its Tailwind and shadcn cards rewritten as FilingLens's CSS, with FilingLens's content | `web/components/overview.tsx`, `web/app/landing.css` | Mohammad Shehadeh, from the Hirael library (https://hirael.com/blocks/features/feature-10, https://github.com/MohammadShehadeh/hirael), via 21st.dev | MIT |
| The table with numeric pagination, Coverage's table and pager since 2026-11-03: the table's frame, head, rows, hover and spacing, and the pager's page line, outline and ghost icon buttons, gap marks and size select, with their sizes and their focus, hover and disabled states, rewritten as FilingLens's CSS in its colour tokens; its `usePagination` ported to `web/lib/pager.ts` (with a fix: no gap mark when every page fits). Its TanStack Table, Radix, Tailwind and shadcn packages are not used | `web/components/coverage-table.tsx`, `web/lib/pager.ts`, `web/app/globals.css` | Origin UI, on 21st.dev; its table, button, pagination and select from shadcn/ui | MIT |
| ShaderGradient, the hero's moving field and, since 2026-11-03, Ask's stage's | `web/components/hero-field.tsx`; npm `@shadergradient/react` 2.4.20 | ruucm | MIT |
| Lucide's icon geometry: monitor, sun, moon, file, file-text, hash, check, play, pause, rotate-ccw, arrow-right, arrow-left, menu, x, route, search, message-square-text, shield-check, chevron-left, chevron-right, chevron-down, ellipsis, drawn inline | `web/app/login/page.tsx` (Back to home), `web/components/theme-toggle.tsx`, `landing-header.tsx`, `story-panel.tsx` (shared with `answer-card.tsx`), `bond.tsx` (shared by `hero-live.tsx` and `ask-live.tsx`), `ask.tsx` (the send arrow), `overview.tsx`, `coverage-table.tsx`, `web/app/page.tsx` | Lucide contributors | ISC; portions from Feather, MIT |
| three.js, React Three Fiber and Motion, bundled into the moving hero's chunks only | npm `three` 0.186.1, `@react-three/fiber` 9.8.2, `motion` 14.3.0 | the three.js authors, Poimandres, Motion | MIT |

Design references, no code copied:

- The landing header follows the header of 21st.dev's "hero4" (logo and name, links, theme toggle, Sign in, one main button, a phone menu), rebuilt in FilingLens's own markup, colours and tokens.
- The landing's "How an answer is made" follows FreightAudit's How it works, and the app's badges, buttons, list table and pager follow FreightAudit's `ui.tsx` and styles (2026-11-03). FreightAudit is the same owner's project, read only; the structure is rebuilt here in FilingLens's own markup, colours and tokens.
- The mark redraws variant #6 of the logo sheet the user made (`H:\Projects\projects\_tmp\logos\filing-lens-logo.png`, outside the repo); the redraw is FilingLens's own (`docs/brand/`, `web/lib/logo.ts`).

## Prompt Bond's licence

MIT License. Copyright (c) Sanjay Kumar (Cojeev), the 000h library.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Hirael's licence

MIT License. Copyright (c) 2026 Mohammad Shehadeh.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Origin UI's and shadcn/ui's licence

The table with numeric pagination (Origin UI, on 21st.dev) and the shadcn/ui parts it is built on are MIT-licensed. Copyright (c) Origin UI; copyright (c) shadcn. The listing the user supplied gave no copyright year.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Lucide's licence

ISC License. Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2026 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2026.

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
