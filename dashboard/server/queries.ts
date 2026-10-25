import { SQL } from "bun";

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

const num = (v: unknown): number => Number(v ?? 0);
const numOrNull = (v: unknown): number | null => (v == null ? null : Math.round(Number(v)));

export function connect(url: string): SQL {
  return new SQL(url);
}

/**
 * All figures for the last `days` days. Every statement runs in one READ ONLY transaction.
 *
 * Latency: a stored 0 means "not measured" (api_lookup and get_related used to log a hard-coded 0),
 * so zeros are left out of every percentile. The headline figure covers the two search tools only;
 * the lookups are in-memory and would drag the median to a meaningless value.
 */
export async function overview(sql: SQL, days: number): Promise<Overview> {
  return sql.begin("read only", async (tx) => {
    const [t] = await tx`
      SELECT
        count(*)                                           AS events,
        count(*) FILTER (WHERE event_type = 'tool_call')   AS tool_calls,
        count(*) FILTER (WHERE event_type = 'resource_read') AS resource_reads,
        count(*) FILTER (WHERE error IS NOT NULL)          AS errors,
        percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE latency_ms > 0 AND name IN ('docs_search', 'ecosystem_search')) AS p50,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE latency_ms > 0 AND name IN ('docs_search', 'ecosystem_search')) AS p95,
        min(timestamp)                                     AS first_event,
        max(timestamp)                                     AS last_event
      FROM usage_events
      WHERE timestamp >= now() - make_interval(days => ${days})`;

    const daily = await tx`
      SELECT d::date::text AS day,
             count(*) FILTER (WHERE e.event_type = 'tool_call')     AS tool_calls,
             count(*) FILTER (WHERE e.event_type = 'resource_read') AS resource_reads
      FROM generate_series(
             date_trunc('day', now() - make_interval(days => ${days - 1})),
             date_trunc('day', now()), interval '1 day') AS d
      LEFT JOIN usage_events e ON date_trunc('day', e.timestamp) = d
      GROUP BY d ORDER BY d`;

    const tools = await tx`
      SELECT name, count(*) AS count,
             percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE latency_ms > 0) AS p50,
             percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE latency_ms > 0) AS p95,
             count(*) FILTER (WHERE error IS NOT NULL) AS errors
      FROM usage_events
      WHERE event_type = 'tool_call' AND timestamp >= now() - make_interval(days => ${days})
      GROUP BY name ORDER BY count DESC`;

    const frameworks = await tx`
      SELECT coalesce(framework, '(all frameworks)') AS framework, count(*) AS count
      FROM usage_events
      WHERE timestamp >= now() - make_interval(days => ${days})
      GROUP BY 1 ORDER BY count DESC LIMIT 20`;

    const topQueries = await tx`
      SELECT lower(trim(query)) AS query, count(*) AS count
      FROM usage_events
      WHERE query IS NOT NULL AND timestamp >= now() - make_interval(days => ${days})
      GROUP BY 1 ORDER BY count DESC, 1 LIMIT 15`;

    const recentErrors = await tx`
      SELECT timestamp::text AS timestamp, name, framework, error
      FROM usage_events
      WHERE error IS NOT NULL AND timestamp >= now() - make_interval(days => ${days})
      ORDER BY timestamp DESC LIMIT 10`;

    const events = num(t.events);
    return {
      days,
      totals: {
        events,
        toolCalls: num(t.tool_calls),
        resourceReads: num(t.resource_reads),
        errors: num(t.errors),
        errorRate: events ? num(t.errors) / events : 0,
        p50Ms: numOrNull(t.p50),
        p95Ms: numOrNull(t.p95),
        firstEvent: t.first_event ? new Date(t.first_event).toISOString() : null,
        lastEvent: t.last_event ? new Date(t.last_event).toISOString() : null,
      },
      daily: daily.map((r: any) => ({
        day: r.day,
        toolCalls: num(r.tool_calls),
        resourceReads: num(r.resource_reads),
      })),
      tools: tools.map((r: any) => ({
        name: r.name,
        count: num(r.count),
        p50Ms: numOrNull(r.p50),
        p95Ms: numOrNull(r.p95),
        errors: num(r.errors),
      })),
      frameworks: frameworks.map((r: any) => ({ framework: r.framework, count: num(r.count) })),
      topQueries: topQueries.map((r: any) => ({ query: r.query, count: num(r.count) })),
      recentErrors: recentErrors.map((r: any) => ({
        timestamp: r.timestamp,
        name: r.name,
        framework: r.framework,
        error: r.error,
      })),
    };
  });
}
