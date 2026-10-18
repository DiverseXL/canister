/**
 * PageHeader: eyebrow label above, large Syne display title, one-line mono
 * description below — the same header rhythm as the landing page.
 */
export default function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: React.ReactNode;
}) {
  return (
    <header className="space-y-3">
      <p className="label text-lp-mute">{eyebrow}</p>
      <h1 className="display text-[clamp(1.875rem,4.5vw,3rem)] leading-[1.02] tracking-[-0.01em] text-lp-ink">
        {title}
      </h1>
      <p className="text-[15px] leading-[1.75] text-lp-mute">{description}</p>
    </header>
  );
}
