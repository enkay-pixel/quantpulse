import { explain, lookup } from "../lib/glossary";

/**
 * A term as the dashboard shows it: the plain name first, the technical name small beneath it,
 * and what it means on hover. Every column header and stat label goes through this, so nothing on
 * the page needs a guidebook — and the technical name is still there to search for or to use
 * with an advisor.
 */
export function Term({
  id,
  label,
  align = "left",
}: {
  id: string;
  /** Overrides the plain name where the context sharpens it ("Live return"), keeping the help. */
  label?: string;
  align?: "left" | "right";
}) {
  const entry = lookup(id);
  return (
    <span
      className={`inline-flex flex-col ${align === "right" ? "items-end" : "items-start"}`}
      title={explain(entry)}
      data-term={id}
    >
      <span className="cursor-help underline decoration-dotted underline-offset-2">
        {label ?? entry.label}
      </span>
      {entry.term ? (
        <span
          className="text-[10px] font-normal normal-case tracking-normal"
          style={{ color: "var(--text-muted)" }}
        >
          {entry.term}
        </span>
      ) : null}
    </span>
  );
}
