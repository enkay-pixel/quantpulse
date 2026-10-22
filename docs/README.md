# QuantPulse documentation

Start here. Everything below is plain markdown, readable on GitHub and in Obsidian.

## Where to look

Every ADR, finding and reference page opens with an **In short** line in plain words — read
that first, and the detail only if you need it.

| If you want | Read |
|---|---|
| What this is and how it's doing | [../README.md](../README.md) |
| Current state, honest numbers, what's next | [roadmap.md](roadmap.md) |
| What each milestone set out to do, and what happened (the current one: [M13, more markets](plans/m13-europe-wave.md)) | [plans/](plans/) |
| How to run it, and what to do when it breaks | [runbook.md](runbook.md) |
| Services, data flow, how the pieces fit | [architecture.md](architecture.md) |
| What a term on the dashboard or in the API means | [glossary.md](glossary.md) |
| What a column means and where it came from | [data-dictionary.md](data-dictionary.md) |
| Why it was built this way — the incident log | [development-history.md](development-history.md) |
| How the ML holds up against a published rubric | [ml-test-score.md](ml-test-score.md) |
| What we measured, and what it did and didn't show | [findings/](findings/README.md) |
| How to measure anything here without fooling yourself | [measurement.md](measurement.md) |
| Decisions that would be expensive to revisit | [adr/](adr/) |
| Working context for coding agents | [../CLAUDE.md](../CLAUDE.md) |

## Using Obsidian

The repository root is an Obsidian vault. Open it with *Open folder as vault* and the docs
above become linked and graphable with no extra setup — there is no separate vault, because
two sets of documentation drift apart.

Committed settings in `.obsidian/app.json` matter:

- **Markdown links, not wikilinks.** `[[Wikilinks]]` render as literal brackets on GitHub, and
  GitHub is where people actually read this. The setting makes Obsidian write
  `[roadmap](roadmap.md)` instead, which both surfaces understand. CI fails on wikilinks in
  tracked files so the rule does not depend on remembering it.
- **Relative link format**, for the same reason.
- **Vendored directories excluded** — `node_modules` alone holds 404 markdown files against
  this project's ~15, and would swamp search and the graph.

Per-machine state (`workspace*.json`, caches, plugin credentials) is gitignored; shared
settings are committed so the rules hold for anyone who opens the vault.

## Writing docs

- Put lasting explanation in these files. Code comments stay general — incidents, dates and
  specific occurrences belong here, where a reader has the context to use them.
- Link generously between documents. Backlinks are most of the value of the vault.
- Numbers age. State when a figure was measured, and what it was measured on.

## Publishing

GitHub already renders all of this publicly, with working links, and that is the public copy.
A separate site was considered and declined on 2026-10-16: [Quartz](https://quartz.jzhao.xyz/)
on GitHub Pages would be free, but it adds only search and a graph view, at the price of a
second published copy to keep correct and a build to maintain. Obsidian Publish would also
cost $8/month, against the zero-cost constraint in [roadmap.md](roadmap.md).
