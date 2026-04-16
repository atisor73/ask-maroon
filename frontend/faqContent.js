export const GITHUB_ISSUES_URL = "https://github.com/atisor73/ask-maroon/issues";

export const UI_ANNOTATIONS = [
  {
    id: "query-guide",
    title: "Search here first",
    text:
      "Type a concept, event, person, or phrase. The model embeds your query, compares it with embedded archive chunks, and ranks the closest matches.",
    leftPct: 2,
    topRem: 7,
    widthRem: 19,
    dotLeftPct: 18.5,
    dotTopRem: 14.75,
  },
  {
    id: "backend-guide",
    title: "Vector backend",
    text:
      "This selects which embedding model powers retrieval. The interface stays the same, but retrieval quality, speed, and availability can vary by backend.",
    leftPct: 1.5,
    topRem: 19.75,
    widthRem: 18,
    dotLeftPct: 13.8,
    dotTopRem: 18.65,
  },
  {
    id: "advanced-guide",
    title: "Advanced search",
    text:
      "Greedy search returns the closest matches directly. Exploratory sampling draws from the strongest candidates so search can keep some spontaneity.",
    leftPct: 19.5,
    topRem: 27,
    widthRem: 20,
    dotLeftPct: 22.5,
    dotTopRem: 24.7,
  },
  {
    id: "sampling-guide",
    title: "Top N + temperature",
    text:
      "Top N controls the pool we sample from. Temperature controls how sharply or loosely we draw from that pool.",
    leftPct: 23,
    topRem: 39,
    widthRem: 18,
    dotLeftPct: 25.2,
    dotTopRem: 29.9,
  },
  {
    id: "results-guide",
    title: "Ranked archive chunks",
    text:
      "Results appear here. We surface the best-matching documents, then use reverse highlighting to show which passages inside the chunk seem most relevant to the query.",
    leftPct: 2,
    topRem: 49,
    widthRem: 20,
    dotLeftPct: 18.5,
    dotTopRem: 35.5,
  },
  {
    id: "viewer-guide",
    title: "Check the source issue",
    text:
      "The right side keeps the original PDF visible so readers can verify context quickly instead of trusting the snippet alone.",
    leftPct: 61.5,
    topRem: 9,
    widthRem: 18,
    dotLeftPct: 67,
    dotTopRem: 15,
  },
  {
    id: "feedback-guide",
    title: "Send feedback",
    text:
      "If people get confused, open an issue so we can tighten the wording or add another annotation.",
    leftPct: 67.5,
    topRem: 32,
    widthRem: 16,
    dotLeftPct: 73,
    dotTopRem: 39,
    linkLabel: "Open GitHub Issues",
    linkHref: GITHUB_ISSUES_URL,
  },
];
