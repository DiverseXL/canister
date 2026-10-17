import Link from "next/link";

const LINKS: [string, string][] = [
  ["#the-problem", "The problem"],
  ["#how-it-works", "How it works"],
  ["#evidence", "Evidence"],
  ["#limits", "Limits"],
  ["#api", "API"],
];

/**
 * Top navigation: tiny letter-spaced monospace labels, an outline button to
 * the gate and a filled button to the repository.
 */
export default function Nav() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 border-b border-lp-line bg-lp-panel px-5 py-4 md:px-8">
      <Link
        href="/"
        className="flex items-center gap-2.5 rounded-sm text-lp-ink"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 18 18"
          aria-hidden="true"
          focusable="false"
          className="shrink-0"
        >
          <rect
            x="1.25"
            y="1.25"
            width="15.5"
            height="15.5"
            rx="4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          />
          <path
            d="M4.5 13.5 L13.5 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
        <span className="display text-[15px] tracking-[0.04em]">Canister</span>
      </Link>

      <nav aria-label="Sections" className="hidden items-center gap-6 md:flex">
        {LINKS.map(([href, label]) => (
          <Link
            key={href}
            href={href}
            className="label rounded-sm text-lp-mute hover:text-lp-ink"
          >
            {label}
          </Link>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <Link
          href="/gate"
          className="label rounded-full border border-lp-ink px-4 py-2 text-lp-ink hover:bg-lp-ink hover:text-lp-bg"
        >
          See the gate
        </Link>
        <a
          href="https://github.com/DiverseXL/canister"
          target="_blank"
          rel="noreferrer"
          className="label rounded-full bg-lp-ink px-4 py-2 text-lp-bg hover:opacity-90"
        >
          View on GitHub
        </a>
      </div>
    </header>
  );
}