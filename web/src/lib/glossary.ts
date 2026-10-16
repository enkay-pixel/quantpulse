import raw from "./glossary.json";

/** One entry of configs/glossary.yaml — copied here by `make glossary`, and kept in step by a test. */
export interface GlossaryEntry {
  label: string;
  meaning: string;
  term?: string;
  read?: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = raw as Record<string, GlossaryEntry>;

/** The entry for a term. Throws on an unknown id: a label with no explanation is a bug to fix in
 * the glossary, not a gap to render around. */
export function lookup(id: string): GlossaryEntry {
  const entry = GLOSSARY[id];
  if (!entry) throw new Error(`No glossary entry for "${id}" — add it to configs/glossary.yaml`);
  return entry;
}

/** What a term means and how to read it, as one line of help text. */
export function explain(entry: GlossaryEntry): string {
  return entry.read ? `${entry.meaning} How to read it: ${entry.read}` : entry.meaning;
}
