/**
 * Footer: one technical sentence, then the credit line.
 */
export default function Footer() {
  return (
    <footer className="border-t border-lp-line bg-lp-panel px-5 py-8 md:px-8">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-2 text-[12px] leading-relaxed text-lp-mute md:flex-row md:items-center md:justify-between">
        <p>
          A temporal claim graph on FalkorDB. Built for Graph Hacks, Track 03.
        </p>
      </div>
    </footer>
  );
}