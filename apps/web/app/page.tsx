import { JetBrains_Mono, Syne } from "next/font/google";

import Footer from "@/components/footer";
import Frame from "@/components/frame";
import Nav from "@/components/nav";
import Section from "@/components/section";

const display = Syne({
  weight: "800",
  subsets: ["latin"],
  display: "swap",
  fallback: ["Segoe UI", "Arial", "sans-serif"],
  variable: "--font-landing-syne",
});

const mono = JetBrains_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
  variable: "--font-landing-mono",
});

export default function Landing() {
  return (
    <div
      className={`landing min-h-screen bg-lp-bg p-3 md:p-5 ${display.variable} ${mono.variable}`}
    >
      <a href="#main" className="skip-link label">
        Skip to content
      </a>
      <Frame>
        <Nav />
        <main id="main">
          <Section>
            <h1 className="display text-[clamp(2.75rem,8vw,6.75rem)] leading-[0.95] tracking-[-0.01em] text-lp-ink">
              Retired facts still rank.{" "}
              <span className="block">
                We keep them <span className="outline-word">out.</span>
              </span>
            </h1>
          </Section>
        </main>
        <Footer />
      </Frame>
    </div>
  );
}