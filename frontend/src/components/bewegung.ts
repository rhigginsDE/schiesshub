/**
 * Scroll-Verhalten für `scrollIntoView`/`scrollTo`: sanft, außer das Gerät wünscht weniger
 * Bewegung (`prefers-reduced-motion`). Die CSS-Regel in `global.css` wirkt auf JS-Scrollen nicht.
 */
export function scrollVerhalten(): ScrollBehavior {
  const weniger =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return weniger ? "auto" : "smooth";
}
