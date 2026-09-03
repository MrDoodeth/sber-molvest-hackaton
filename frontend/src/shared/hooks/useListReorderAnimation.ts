import { useLayoutEffect, useRef } from "react";

export function useListReorderAnimation<T extends HTMLElement>(order: readonly string[]) {
  const containerRef = useRef<T>(null);
  const positionsRef = useRef<Map<string, DOMRect>>();
  const orderKey = order.join("|");

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const elements = Array.from(
      container.querySelectorAll<HTMLElement>("[data-reorder-id]"),
    );
    const previousPositions = new Map<string, DOMRect>();
    for (const element of elements) {
      const id = element.dataset.reorderId;
      if (id) previousPositions.set(id, element.getBoundingClientRect());
    }

    const previous = positionsRef.current;
    if (previous && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      for (const element of elements) {
        const id = element.dataset.reorderId;
        const before = id ? previous.get(id) : undefined;
        if (!before) continue;
        const after = element.getBoundingClientRect();
        const deltaX = before.left - after.left;
        const deltaY = before.top - after.top;
        if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) continue;
        element.animate(
          [
            { transform: `translate(${deltaX}px, ${deltaY}px)` },
            { transform: "translate(0, 0)" },
          ],
          { duration: 260, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
      }
    }
    positionsRef.current = previousPositions;
  }, [orderKey]);

  return containerRef;
}
