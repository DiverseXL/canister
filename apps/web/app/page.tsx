import Link from "next/link";
import CaseCard from "@/components/case-card";
import { display, mono } from "@/components/fonts";
import Footer from "@/components/footer";
import Frame from "@/components/frame";
import GraphSession from "@/components/graph-session";
import HowItWorks from "@/components/how-it-works";
import Nav from "@/components/nav";
import Section from "@/components/section";

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
          {/* Hero Section */}
          <Section className="pt-12 pb-16 md:pt-16 md:pb-24">
            <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2 lg:gap-14">
              {/* Left: Headline & Actions */}
              <div className="space-y-6">
                <p className="label text-lp-mute">
                  Temporal claim graph on FalkorDB
                </p>
                <h1 className="display text-3xl sm:text-4xl lg:text-[2.65rem] lg:leading-[1.1] tracking-[-0.015em] text-lp-ink">
                  Retired facts still rank.{" "}
                  <span className="block">
                    We keep them <span className="outline-word">out.</span>
                  </span>
                </h1>
                <p className="max-w-[52ch] text-[15px] sm:text-base leading-[1.8] text-lp-mute">
                  Canister sits between your retriever and your model. FalkorDB
                  decides which of the top ten documents may still ground a
                  current answer, and every decision ships with a record you can
                  replay.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <Link
                    href="#how-it-works"
                    className="label inline-flex items-center justify-center rounded-full bg-lp-ink px-5 py-3 text-lp-bg hover:opacity-90 transition-opacity"
                  >
                    Watch the gate cut
                  </Link>
                  <Link
                    href="#api"
                    className="label inline-flex items-center justify-center rounded-full border border-lp-line px-5 py-3 text-lp-ink hover:border-lp-ink transition-colors"
                  >
                    See the API
                  </Link>
                </div>
              </div>

              {/* Right: Case Card */}
              <div>
                <CaseCard />
              </div>
            </div>
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

          <Section id="ask-the-graph" className="border-t border-lp-line">
            <GraphSession />
          </Section>
        </main>
        <Footer />
      </Frame>
    </div>
  );
}
