/** Whether a message is a plain question about past projects that can go straight to the evidence search, skipping the
 * step that works out what the planner wants (about 9 s on the local model). Anything that could be about the plan, a
 * statistic or a follow-up to an earlier turn returns false and takes the full route, so a wrong guess costs time, not a wrong answer. */
const QUESTION = /^(what|why|how|which|who|when|where|were|was|did|does|do|is|are|can|could|has|have|had|tell me|explain)\b/i;
// a statistic (a table is the answer), or a plan edit or request about the plan
const NOT_EVIDENCE = /\b(slowest|fastest|longest|shortest|average|median|rank|ranking|compare|how long|how many|how often|percent|per cent|top \d+|by (country|method|sector|region|year)|plan|package|packages|forecast|deadline|bottleneck|schedule|timeline|add|change|set|make|update|switch|remove|delete|start|budget|value)\b/i;
// refers back to the conversation or to the plan on the right
const REFERS_BACK = /\b(it|its|them|they|this|that|these|those|my|our|above|earlier|before|same|instead|also)\b/i;

export function isEvidenceQuestion(text: string): boolean {
  const t = text.trim();
  if (t.length < 12 || t.length > 400) return false;
  if (!QUESTION.test(t)) return false;   // "and for India?" and other follow-ups start differently
  return !NOT_EVIDENCE.test(t) && !REFERS_BACK.test(t);
}
