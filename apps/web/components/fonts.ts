import { JetBrains_Mono, Syne } from "next/font/google";

export const display = Syne({
  weight: "800",
  subsets: ["latin"],
  display: "swap",
  fallback: ["Segoe UI", "Arial", "sans-serif"],
  variable: "--font-landing-syne",
});

export const mono = JetBrains_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
  variable: "--font-landing-mono",
});
