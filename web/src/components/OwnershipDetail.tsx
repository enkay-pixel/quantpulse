import type { OwnershipDetailOut } from "../api/types";
import { formatDate, formatMoney, formatPercent, formatUsdCompact } from "../lib/format";
import { Term } from "./Term";

const TH = "px-3 py-2 font-medium";

/** One stock's open-market insider trades over the past year and its holders over 5%. */
export function OwnershipDetail({ data }: { data: OwnershipDetailOut }) {
  return (
    <div className="space-y-4">
      {data.holders.length ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              <th className={`${TH} text-left`}><Term id="filer" /></th>
              <th className={`${TH} text-left`}><Term id="form" /></th>
              <th className={`${TH} text-left`}><Term id="filed" /></th>
              <th className={`${TH} text-right`}><Term id="percent" align="right" /></th>
            </tr>
          </thead>
          <tbody>
            {data.holders.map((h) => (
              <tr key={h.filer} className="border-t" style={{ borderColor: "var(--grid)" }}>
                <td className="px-3 py-1.5">{h.filer}</td>
                <td className="px-3 py-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                  {h.form.replace("SCHEDULE ", "")}
                </td>
                <td className="px-3 py-1.5">{formatDate(h.filed)}</td>
                <td className="px-3 py-1.5 text-right tabular">{formatPercent(h.percent / 100, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          No holder has a current filing reporting over 5%.
        </p>
      )}
      {data.trades.length ? (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0" style={{ background: "var(--surface-1)" }}>
              <tr className="text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                <th className={`${TH} text-left`}><Term id="transaction_date" /></th>
                <th className={`${TH} text-left`}><Term id="owner" /></th>
                <th className={`${TH} text-left`}><Term id="trade" /></th>
                <th className={`${TH} text-right`}><Term id="value_usd" align="right" /></th>
                <th className={`${TH} text-right`}><Term id="trade_price" align="right" /></th>
                <th className={`${TH} text-left`}><Term id="planned" /></th>
              </tr>
            </thead>
            <tbody>
              {data.trades.map((t, i) => (
                <tr key={`${t.transaction_date}-${t.owner}-${i}`} className="border-t" style={{ borderColor: "var(--grid)" }}>
                  <td className="px-3 py-1.5">{formatDate(t.transaction_date)}</td>
                  <td className="px-3 py-1.5">
                    {t.owner}
                    <span className="ml-1 text-xs" style={{ color: "var(--text-muted)" }}>
                      {t.role}
                    </span>
                  </td>
                  <td className="px-3 py-1.5" style={{ color: t.trade === "bought" ? "var(--text-primary)" : "var(--text-secondary)" }}>
                    {t.trade}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular">{formatUsdCompact(t.value_usd)}</td>
                  <td className="px-3 py-1.5 text-right tabular">{formatMoney(t.trade_price)}</td>
                  <td className="px-3 py-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
                    {t.planned === null ? "—" : t.planned ? "yes" : "no"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          No open-market insider trade in the past year.
        </p>
      )}
    </div>
  );
}
