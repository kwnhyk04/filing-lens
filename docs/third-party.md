# Third-party code and assets

Code and designs FilingLens's web app takes from others, beyond what its npm packages carry themselves.

| What | Where | From | Licence |
| --- | --- | --- | --- |
| Prompt Bond, the hero's moving story: the membrane's shader and renderer, the organisms' steering, the layout and scatter, the beat timelines and the frame loop, adapted to one FilingLens answer | `web/components/hero-live.tsx`, `web/components/hero-live.css` | Sanjay Kumar (Cojeev), from the 000h library, via 21st.dev: https://21st.dev/@luv-jeri_c92deb60/components/prompt-bond | MIT |
| ShaderGradient, the hero's moving field | `web/components/hero-field.tsx`; npm `@shadergradient/react` 2.4.20 | ruucm | MIT |
| Lucide's icon geometry: monitor, sun, moon, file, file-text, check, play, pause, rotate-ccw, arrow-right, menu, x | `web/components/theme-toggle.tsx`, `landing-header.tsx`, `story-panel.tsx`, `hero-live.tsx` | Lucide contributors | ISC; portions from Feather, MIT |
| three.js, React Three Fiber and Motion, bundled into the moving hero's chunks only | npm `three` 0.186.1, `@react-three/fiber` 9.8.2, `motion` 14.3.0 | the three.js authors, Poimandres, Motion | MIT |

Design references, no code copied:

- The landing header follows the header of 21st.dev's "hero4" (logo and name, links, theme toggle, Sign in, one main button, a phone menu), rebuilt in FilingLens's own markup, colours and tokens.
- The mark redraws variant #6 of the logo sheet the user made (`H:\Projects\projects\_tmp\logos\filing-lens-logo.png`, outside the repo); the redraw is FilingLens's own (`docs/brand/`, `web/lib/logo.ts`).

## Prompt Bond's licence

MIT License. Copyright (c) Sanjay Kumar (Cojeev), the 000h library.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Lucide's licence

ISC License. Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2026 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2026.

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
