-- Synthetic usage traffic for LOCAL development only. Never run against production.
--   psql postgresql://vue_mcp:vue_mcp@localhost:5432/vue_mcp -f dashboard/seed.sql
-- Re-running replaces all usage_events.
TRUNCATE usage_events RESTART IDENTITY;

INSERT INTO usage_events (timestamp, event_type, name, query, framework, latency_ms, response_chars, error)
SELECT
  ts,
  CASE WHEN r_type < 0.22 THEN 'resource_read' ELSE 'tool_call' END,
  CASE
    WHEN r_type < 0.22 THEN fw || '://pages/' || (ARRAY['guide/essentials/computed.md','api/composition-api-setup.md','core-concepts/state.md','guide/essentials/watchers.md'])[1 + floor(random()*4)::int]
    WHEN r_tool < 0.70 THEN 'docs_search'
    WHEN r_tool < 0.86 THEN 'api_lookup'
    WHEN r_tool < 0.95 THEN 'get_related'
    ELSE 'ecosystem_search'
  END,
  CASE WHEN r_type >= 0.22 AND r_tool < 0.70 THEN
    (ARRAY['how do I use computed properties','watch vs watchEffect','navigation guards','define a store with setup syntax','debounce a ref','useFetch data fetching','environment variables and modes','custom validation rules','provide inject','teleport modal','v-model on custom components','lazy loading routes','pinia persist state','vitest mock modules','form submission handling'])[1 + floor(random()*15)::int]
  END,
  fw,
  (60 + (-ln(1 - random()) * 380))::int,
  (800 + floor(random() * 9000))::int,
  CASE WHEN random() < 0.012 THEN 'upstream timeout' END
FROM (
  SELECT
    ts,
    random() AS r_type,
    random() AS r_tool,
    (ARRAY['vue','vue','vue','vue','vue-router','vue-router','pinia','pinia','nuxt','nuxt','vueuse','vite','vitest','formkit','shadcn-vue','vitepress','vee-validate','pinia-colada','vue-flow','vue-devtools'])[1 + floor(random()*20)::int] AS fw
  FROM (
    SELECT
      now() - make_interval(secs => random() * 30 * 86400) AS ts
    FROM generate_series(1, 14000)
  ) raw
  -- growth: later days get more events, weekends fewer
  WHERE random() < (0.35 + 0.65 * (1 - extract(epoch FROM (now() - ts)) / (30 * 86400)))
    AND (extract(isodow FROM ts) < 6 OR random() < 0.45)
) t;

SELECT count(*) AS seeded_events, min(timestamp)::date AS first_day, max(timestamp)::date AS last_day FROM usage_events;
