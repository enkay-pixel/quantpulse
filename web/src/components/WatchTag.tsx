/** Marks a research-watchlist name in a table of the model's names (ADR 0007): followed by the
 * research pages only, never a model input. */
export function WatchTag({ followedBy }: { followedBy?: string }) {
  if (followedBy !== "watchlist") return null;
  return (
    <span
      className="ml-1.5 rounded px-1 align-middle text-[10px] uppercase tracking-wide"
      style={{ border: "1px solid var(--border)", color: "var(--text-muted)" }}
      title="On the research watchlist: followed by these pages only, never by the model"
    >
      watchlist
    </span>
  );
}
