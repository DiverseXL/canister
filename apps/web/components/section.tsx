/**
 * Section: one vertical rhythm (16/24 spacing scale) and one width (1100px)
 * for every block of the landing page.
 */
export default function Section({
  id,
  className = "",
  children,
}: {
  id?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      id={id}
      className={`mx-auto w-full max-w-[1100px] px-6 py-16 md:px-8 md:py-24 ${className}`}
    >
      {children}
    </section>
  );
}