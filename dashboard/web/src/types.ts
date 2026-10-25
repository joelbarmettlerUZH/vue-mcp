export interface Overview {
  days: number;
  totals: {
    events: number;
    toolCalls: number;
    resourceReads: number;
    errors: number;
    errorRate: number;
    p50Ms: number | null;
    p95Ms: number | null;
    firstEvent: string | null;
    lastEvent: string | null;
  };
  daily: { day: string; toolCalls: number; resourceReads: number }[];
  tools: { name: string; count: number; p50Ms: number | null; p95Ms: number | null; errors: number }[];
  frameworks: { framework: string; count: number }[];
  topQueries: { query: string; count: number }[];
  recentErrors: { timestamp: string; name: string; framework: string | null; error: string }[];
}
