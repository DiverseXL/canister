import Footer from "@/components/footer";
import Frame from "@/components/frame";
import { display, mono } from "@/components/fonts";
import Nav from "@/components/nav";
import Section from "@/components/section";

export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
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
          <Section>{children}</Section>
        </main>
        <Footer />
      </Frame>
    </div>
  );
}
