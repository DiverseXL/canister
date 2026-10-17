import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Canister console",
  description:
    "Temporal claim graph on FalkorDB: superseded facts never ground a present-tense answer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}