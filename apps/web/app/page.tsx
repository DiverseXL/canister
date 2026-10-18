import { JetBrains_Mono, Syne } from "next/font/google";

import Footer from "@/components/footer";
import Frame from "@/components/frame";
import HowItWorks from "@/components/how-it-works";
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

          <Section id="the-problem" className="border-t border-lp-line">
            <div className="grid gap-8 md:grid-cols-[170px_minmax(0,1fr)] md:gap-14">
              <p className="label text-lp-mute">01 — The problem</p>
              <div className="max-w-[64ch] space-y-6">
                <h2 className="display text-[clamp(1.5rem,3.2vw,2.4rem)] leading-[1.1] tracking-[-0.005em] text-lp-ink">
                  A pile of claims with lifetimes.
                </h2>
                <p className="text-[15px] leading-[1.85] text-lp-mute">
                  A company’s knowledge is not a pile of facts. It is a pile of{" "}
                  <span className="text-lp-ink">claims with lifetimes</span>: a
                  price is right on Monday, replaced on Wednesday, historically
                  true on Friday, and harmful if an agent quotes it as current a
                  month later.
                </p>
                <p className="text-[15px] leading-[1.85] text-lp-mute">
                  Retrieval is built to maximise relevance, and that creates a
                  specific failure. The retired document and the current
                  document were written by the same people, about the same
                  system, in the same vocabulary, so the retired one ranks just
                  as well, and often better because it has had more time to be
                  repeated. On our corpus, plain BM25 leaks{" "}
                  <span className="text-lp-ink">
                    43 superseded documents into the top 10 across 18 conflict
                    questions
                  </span>. The agent then reads old truth as if it were new.
                </p>
                <p className="text-[15px] leading-[1.85] text-lp-mute">
                  Canister treats “this used to be true” as a first-class state
                  that sits next to relevance, so retired truth stays visible as
                  history and unreachable as present.
                </p>
              </div>
            </div>
          </Section>

          <Section id="how-it-works" className="border-t border-lp-line">
            <HowItWorks />
          </Section>
        </main>
        <Footer />
      </Frame>
    </div>
  );
}
