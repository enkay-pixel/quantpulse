import type { FindingsOut } from "../api/types";

/**
 * Every investigation, by its question and what came back.
 *
 * Read from the findings index itself rather than a copy, so the page cannot drift from the
 * write-ups. Several outcomes record a claim that was later withdrawn; that is the record
 * working, and the full account is one link away.
 */
export function FindingsList({ data }: { data: FindingsOut }) {
  if (data.findings.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        No findings index available.
      </p>
    );
  }
  return (
    <ul className="divide-y" style={{ borderColor: "var(--grid)" }}>
      {data.findings.map((f) => (
        <li key={f.url} className="py-3">
          <a
            href={f.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium hover:underline"
            style={{ color: "var(--text-primary)" }}
          >
            {f.title}
          </a>
          <p className="mt-0.5 text-xs italic" style={{ color: "var(--text-muted)" }}>
            {f.question}
          </p>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            {f.outcome}
          </p>
        </li>
      ))}
    </ul>
  );
}
