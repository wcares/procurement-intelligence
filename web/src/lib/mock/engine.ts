import "server-only";

import data from "@/mocks/data.json";
import type {
  AnswerSentence,
  AskRequest,
  AskResponse,
  AssessRequest,
  AssessResponse,
  Citation,
  GovernanceScore,
  Options,
  Precedent,
  RiskFlag,
  TimelineBenchmark,
} from "@/lib/api/types";

// Fixtures exported by `python -m procintel.export_mock` from data/procintel.duckdb.
type Bench = { n: number; median: number; p25: number; p75: number; p90: number; shareOver180: number };
type Passage = Citation & { region: string; procGroups: string[]; score: number };

const benchmarks = data.benchmarks as Record<string, Bench | null>;
const governance = data.governance as Record<string, GovernanceScore[]>;
const passages = data.passages as Passage[];
const countries = new Map(data.options.countries.map((c) => [c.code, c]));

const MIN_N = 10;
const STOP = new Set(
  "the and for with that this from what why how are was were have has had into over under about which their there they them been more most than when where does did not any all can will".split(" "),
);

function meta(caveats: string[]) {
  return { source: "mock" as const, generatedAt: new Date().toISOString(), caveats, responseId: crypto.randomUUID() };
}

function tokens(s: string): string[] {
  return (s.toLowerCase().match(/[a-z][a-z-]{3,}/g) ?? []).filter((t) => !STOP.has(t));
}

export function options(): Options {
  return data.options as Options;
}

function timeline(req: AssessRequest): TimelineBenchmark | null {
  const label = (k: string) => data.options.procGroups.find((g) => g.code === k)?.label ?? k;
  const scopes: [string, string][] = [
    [`${req.procGroup}/${req.methodCode}`, `${label(req.procGroup)} via ${req.methodCode}`],
    [req.procGroup, `all ${label(req.procGroup)} packages`],
    ["all", "all packages"],
  ];
  for (const [key, scope] of scopes) {
    const b = benchmarks[key];
    if (b && b.n >= MIN_N) {
      return { metric: "tender_to_award_days", scope, n: b.n, median: b.median, p25: b.p25, p75: b.p75, p90: b.p90 };
    }
  }
  return null;
}

function risks(req: AssessRequest, t: TimelineBenchmark | null, gov: GovernanceScore[]): RiskFlag[] {
  const out: RiskFlag[] = [];
  const key = benchmarks[`${req.procGroup}/${req.methodCode}`] ? `${req.procGroup}/${req.methodCode}` : req.procGroup;
  const b = benchmarks[key];
  if (b && b.n >= MIN_N) {
    const pct = Math.round(b.shareOver180 * 100);
    out.push({
      id: "long-cycle",
      label: "Award takes longer than 6 months",
      level: b.shareOver180 > 0.35 ? "high" : b.shareOver180 > 0.2 ? "medium" : "low",
      basis: "statistic",
      detail: `${pct}% of ${b.n} comparable packages took more than 180 days from tender notice to award.`,
    });
  }
  if (t && t.median > 0 && t.p90 / t.median > 2.5) {
    out.push({
      id: "spread",
      label: "Unpredictable timeline",
      level: "medium",
      basis: "statistic",
      detail: `The slowest 10% took over ${Math.round(t.p90)} days, ${(t.p90 / t.median).toFixed(1)}× the median of ${Math.round(t.median)}. Plan buffer time.`,
    });
  }
  const tran = gov.find((g) => g.indicator === "transparency_corruption");
  if (tran && tran.value < 3) {
    out.push({
      id: "governance",
      label: "Low public-sector transparency score",
      level: tran.value < 2.5 ? "high" : "medium",
      basis: "statistic",
      detail: `CPIA transparency/corruption rating ${tran.value} (${tran.year}) on a 1–6 scale. Consider more prior review.`,
    });
  }
  return out;
}

function precedents(req: AssessRequest): Precedent[] {
  const region = countries.get(req.countryCode)?.region;
  const want = new Set(tokens(`${req.description ?? ""} ${req.sector ?? ""}`));
  const scored = passages.map((p) => {
    const matchedOn: string[] = [];
    let s = 0;
    const add = (points: number, why: string) => {
      s += points;
      matchedOn.push(why);
    };
    if (p.countryCode === req.countryCode) add(3, "same country");
    else if (region && p.region === region) add(1.5, "same region");
    if (p.procGroups.includes(req.procGroup)) add(2, "same procurement type");
    const uniq = [...new Set(tokens(p.quote).filter((t) => want.has(t)))];
    if (uniq.length) add(Math.min(3, uniq.length * 0.5), `terms: ${uniq.slice(0, 4).join(", ")}`);
    return { p, s, matchedOn };
  });
  return scored
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || b.p.score - a.p.score)
    .slice(0, 5)
    .map(({ p, s, matchedOn }) => ({ citation: toCitation(p), relevance: Math.min(1, s / 8), matchedOn }));
}

function toCitation(p: Passage): Citation {
  const { id, docId, docType, title, section, quote, url, projectId, projectName, countryCode } = p;
  return { id, docId, docType, title, section, quote, url, projectId, projectName, countryCode };
}

export function assess(req: AssessRequest): AssessResponse {
  const gov = governance[req.countryCode] ?? [];
  const t = timeline(req);
  return {
    timeline: t,
    risks: risks(req, t, gov),
    governance: gov,
    precedents: precedents(req),
    similarPackages: [],
    meta: meta([
      "Mock response: numbers are real historical statistics from the 120-ICR sample; precedents are ranked by a simple keyword match, not the production retriever.",
      ...(gov.length ? [] : ["No CPIA governance scores are available for this country."]),
      ...(t && !t.scope.includes(" via ") ? ["Too few packages for this exact method; the timeline uses a wider slice."] : []),
    ]),
  };
}

export function ask(req: AskRequest): AskResponse {
  const q = new Set(tokens(req.question));
  const ranked = passages
    .filter((p) => !req.countryCode || p.countryCode === req.countryCode)
    .filter((p) => !req.procGroup || p.procGroups.includes(req.procGroup))
    .map((p) => ({ p, hits: new Set(tokens(p.quote).filter((t) => q.has(t))).size }))
    .filter((x) => x.hits >= 2)
    .sort((a, b) => b.hits - a.hits)
    .slice(0, 3);

  const citations: Citation[] = [];
  const answer: AnswerSentence[] = [];
  for (const { p } of ranked) {
    // the answer is the best-matching sentence quoted verbatim, so it cannot say more than the source
    const sentences = p.quote.split(/(?<=[.;])\s+(?=[A-Z0-9])/);
    const best = sentences
      .map((s) => ({ s, hits: tokens(s).filter((t) => q.has(t)).length }))
      .sort((a, b) => b.hits - a.hits)[0];
    if (!best || best.hits === 0) continue;
    citations.push(toCitation(p));
    answer.push({ text: best.s.trim(), citations: [citations.length - 1] });
  }
  return {
    answer,
    citations,
    unsupported: answer.length === 0,
    meta: meta([
      "Mock response: each sentence is a verbatim quote from an ICR, chosen by keyword overlap. No language model is involved yet.",
    ]),
  };
}
