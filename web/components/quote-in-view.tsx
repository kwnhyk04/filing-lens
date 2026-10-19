"use client";
// After a citation's jump to its source card, the cited words come into view inside the sources panel.
import { useEffect } from "react";

export function QuoteInView() {
  useEffect(() => {
    function show(event: MouseEvent) {
      const link = (event.target as Element).closest<HTMLAnchorElement>("a[href^='#']");
      const card = link && document.getElementById(link.hash.slice(1));
      const quote = card?.matches(".card") ? card.querySelector("mark") : null;
      const panel = quote?.closest<HTMLElement>(".sources");
      if (!quote || !panel) return;
      // A frame later the jump has scrolled the panel to the card; this moves only the panel, never the page.
      requestAnimationFrame(() => {
        const box = panel.getBoundingClientRect();
        const at = quote.getBoundingClientRect();
        if (at.top < box.top || at.bottom > box.bottom) panel.scrollTop += at.top - box.top - (box.height - at.height) / 2;
      });
    }
    document.addEventListener("click", show);
    return () => document.removeEventListener("click", show);
  }, []);
  return null;
}
