import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0b0f14",
        panel: "#121821",
        edge: "#22303f",
        current: "#38d39f",
        retired: "#f2705a",
        contest: "#e0b341",
        // Landing page design tokens, defined as CSS variables in globals.css.
        "lp-bg": "var(--lp-bg)",
        "lp-panel": "var(--lp-panel)",
        "lp-line": "var(--lp-line)",
        "lp-ink": "var(--lp-ink)",
        "lp-mute": "var(--lp-mute)",
        "lp-retired": "var(--lp-retired)",
        "lp-current": "var(--lp-current)",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;