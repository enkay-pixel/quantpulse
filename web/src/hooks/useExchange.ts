import { useEffect, useState } from "react";

// The selected market lives in the URL query string, alongside the tab hash, so a view is
// shareable and the browser's back button works. Kept separate from the tab: switching
// market should preserve which tab you were on, and vice versa.
const PARAM = "market";
export const DEFAULT_EXCHANGE = "XNYS";

function fromUrl(): string {
  return new URLSearchParams(window.location.search).get(PARAM) ?? DEFAULT_EXCHANGE;
}

export function useExchange(): [string, (code: string) => void] {
  const [exchange, setExchange] = useState(fromUrl);

  useEffect(() => {
    const onPop = () => setExchange(fromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const select = (code: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set(PARAM, code);
    window.history.pushState({}, "", url);
    setExchange(code);
  };

  return [exchange, select];
}
