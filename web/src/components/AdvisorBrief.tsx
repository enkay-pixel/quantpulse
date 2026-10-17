import type { BriefOut } from "../api/types";
import { formatDate } from "../lib/format";
import { lookup } from "../lib/glossary";
import { WatchTag } from "./WatchTag";

function Points({ id, points, empty }: { id: string; points: string[]; empty: string }) {
  return (
    <div className="brief-block">
      <h3 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        {lookup(id).label}
      </h3>
      {points.length ? (
        <ul className="list-disc space-y-1 pl-5 text-sm" style={{ color: "var(--text-secondary)" }}>
          {points.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {empty}
        </p>
      )}
    </div>
  );
}

/**
 * One stock's advisor brief: the evidence, the points that lean each way, the risks, questions to
 * ask and the limits — laid out to print on one or two pages and take to a licensed advisor.
 */
export function AdvisorBrief({ data }: { data: BriefOut }) {
  return (
    <article className="card brief space-y-4 p-5" data-testid="advisor-brief">
      <header>
        <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          {data.ticker}
          {data.name ? (
            <span className="ml-2 text-sm font-normal" style={{ color: "var(--text-secondary)" }}>
              {data.name}
            </span>
          ) : null}
          <WatchTag followedBy={data.followed_by} />
        </h2>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {data.exchange} · evidence through {formatDate(data.as_of)} · prepared by QuantPulse from
          public data
        </p>
      </header>
      <p className="text-sm" style={{ color: "var(--text-primary)" }}>
        {data.summary}
      </p>
      <div className="brief-block">
        <h3 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {lookup("facts").label}
        </h3>
        <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[minmax(10rem,auto)_1fr]">
          {data.facts.map((f) => (
            <div key={f.fact} className="contents">
              <dt style={{ color: "var(--text-muted)" }}>{f.fact}</dt>
              <dd style={{ color: "var(--text-primary)" }}>
                {f.value}
                {f.note ? (
                  <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    {f.note}
                  </span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Points id="for_points" points={data.for_points} empty="Nothing in the evidence leans this way." />
        <Points id="against_points" points={data.against_points} empty="Nothing in the evidence leans this way." />
      </div>
      <Points id="risks" points={data.risks} empty="No risk beyond those of owning any single stock stood out." />
      <Points id="questions" points={data.questions} empty="" />
      <Points id="limits" points={data.limits} empty="" />
      <p className="border-t pt-3 text-xs" style={{ borderColor: "var(--grid)", color: "var(--text-muted)" }}>
        {data.disclaimer}
      </p>
    </article>
  );
}
