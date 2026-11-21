import "@testing-library/jest-dom/vitest";
import "../i18n";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Mantine fragt Bildschirmbreite und Elementgrößen ab; jsdom kennt beides nicht.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

class ResizeObserverErsatz {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverErsatz;
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
