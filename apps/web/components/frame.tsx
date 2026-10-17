/**
 * Frame: the inset, rounded, hairline-bordered container the landing page
 * lives in. Thin borders only — no shadows, no gradients.
 */
export default function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[28px] border border-lp-line bg-lp-bg">
      {children}
    </div>
  );
}