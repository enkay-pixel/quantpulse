import { useEffect, useState } from "react";

import type { UniverseMember } from "../api/types";

// The Price tile is always alive: with no manual selection it auto-rotates through
// the signal tickers so it never sits on an empty placeholder. A click pins a ticker
// (intentional), and because that intent is worth honoring the pin holds for a longer
// window before rotation quietly resumes.
export const ROTATE_MS = 45_000; // advance through the signal list
export const PIN_MS = 300_000; // a manual pick stays put this long, then rotation resumes

/** What the Price tile cycles through: today's forecasts, strongest first. A market whose first
 * model did not clear the promotion gate has no forecasts, but its prices are still worth
 * showing, so it cycles through the market's stocks instead. Nothing while the forecasts are
 * still loading, so a market with a model never shows its listings first. */
export function priceTickers(
  forecasts: string[] | undefined,
  universe: UniverseMember[] | undefined,
  exchange: string,
): string[] {
  if (forecasts === undefined || forecasts.length > 0) return forecasts ?? [];
  return (universe ?? [])
    .filter((m) => m.exchange === exchange && m.active && m.asset_type === "stock")
    .map((m) => m.ticker);
}

interface Options {
  rotateMs?: number;
  pinMs?: number;
}

interface Rotating {
  ticker: string | null;
  isPinned: boolean;
  pin: (ticker: string) => void;
}

export function useRotatingTicker(tickers: string[], opts: Options = {}): Rotating {
  const rotateMs = opts.rotateMs ?? ROTATE_MS;
  const pinMs = opts.pinMs ?? PIN_MS;

  const [index, setIndex] = useState(0);
  const [pin, setPin] = useState<{ ticker: string; at: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (tickers.length === 0) return;
    const id = setInterval(() => {
      setNow(Date.now());
      setIndex((i) => (i + 1) % tickers.length);
    }, rotateMs);
    return () => clearInterval(id);
  }, [tickers.length, rotateMs]);

  const pinnedActive = pin !== null && now - pin.at < pinMs;
  const ticker = pinnedActive ? pin.ticker : (tickers[index % tickers.length] ?? null);

  return {
    ticker,
    isPinned: pinnedActive,
    pin: (t: string) => {
      setPin({ ticker: t, at: Date.now() });
      setNow(Date.now());
    },
  };
}
