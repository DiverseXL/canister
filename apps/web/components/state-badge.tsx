const BADGES: Record<string, string> = {
  CANON: "border-lp-line text-lp-ink",
  CONTESTED: "border-lp-mute text-lp-mute border-dashed",
  UNKNOWN: "border-lp-mute text-lp-mute border-dotted",
};

/**
 * StateBadge: the decision word with a hairline border — CANON in ink with a
 * solid border, CONTESTED in mute dashed, UNKNOWN in mute dotted. The state is
 * always the word itself, never colour alone.
 */
export default function StateBadge({ state }: { state: string }) {
  const style = BADGES[state];
  if (!style) {
    return <span className="font-mono">{state}</span>;
  }
  return (
    <span
      className={`label inline-block whitespace-nowrap rounded-sm border px-1.5 py-0.5 ${style}`}
    >
      {state}
    </span>
  );
}
