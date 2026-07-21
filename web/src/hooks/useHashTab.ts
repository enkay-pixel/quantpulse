import { useEffect, useState } from "react";

// Tabs live in the URL hash so a view is shareable and bookmarkable
// (e.g. /#evidence), browser back/forward works, and docs can link straight
// to a specific tab.
export function slugify(tab: string): string {
  return tab.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function useHashTab(tabs: string[]): [string, (tab: string) => void] {
  const fromHash = (): string => {
    const slug = window.location.hash.replace(/^#/, "");
    return tabs.find((t) => slugify(t) === slug) ?? tabs[0];
  };

  const [tab, setTab] = useState(fromHash);

  useEffect(() => {
    const onHashChange = () => setTab(fromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabs.join("|")]);

  const select = (next: string) => {
    window.location.hash = slugify(next);
    setTab(next);
  };

  return [tab, select];
}
