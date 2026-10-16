import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Canister console",
  description:
    "Temporal claim graph on FalkorDB: superseded facts never ground a present-tense answer.",
};

const NAV: [string, string][] = [
  ["/", "Overview"],
  ["/cut", "Temporal Cut"],
  ["/truth", "Truth"],
  ["/ask", "Ask"],
  ["/results", "Results"],
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-edge bg-panel">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
            <Link href="/" className="font-mono text-lg font-semibold text-current">
              canister
            </Link>
            <nav className="flex gap-4 text-sm text-slate-300">
              {NAV.map(([href, label]) => (
                <Link key={href} href={href} className="hover:text-white">
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 pb-10 pt-4 text-xs text-slate-500">
          Synthetic, seeded corpus. Every number is read from the API or
          <span className="font-mono"> var/*.json</span>. No hardcoded figures.
        </footer>
      </body>
    </html>
  );
}
