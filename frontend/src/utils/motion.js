/** True when the user asked their system for less motion; animations are then skipped. */
export function prefersReducedMotion() {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}
