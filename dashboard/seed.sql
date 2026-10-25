-- Synthetic usage traffic for LOCAL development only. Never run against production.
--   psql postgresql://vue_mcp:vue_mcp@localhost:5432/vue_mcp -f dashboard/seed.sql
-- Re-running replaces all usage_events. Mimics production history: lookups logged before the
-- latency fix carry latency_ms = 0 ("not measured"); newer ones carry 1-4 ms.
TRUNCATE usage_events RESTART IDENTITY;

INSERT INTO usage_events (timestamp, event_type, name, query, framework, latency_ms, response_chars, error)
SELECT
  ts,
  CASE WHEN tool = 'resource' THEN 'resource_read' ELSE 'tool_call' END,
  CASE WHEN tool = 'resource'
       THEN fw || '://pages/' || (ARRAY['guide/essentials/computed.md','api/composition-api-setup.md','core-concepts/state.md','guide/essentials/watchers.md'])[1 + floor(random()*4)::int]
       ELSE tool END,
  CASE WHEN tool IN ('docs_search', 'ecosystem_search') THEN
    (ARRAY['how do I use computed properties','watch vs watchEffect','navigation guards','define a store with setup syntax','debounce a ref','useFetch data fetching','environment variables and modes','custom validation rules','provide inject','teleport modal','v-model on custom components','lazy loading routes','pinia persist state','vitest mock modules','form submission handling'])[1 + floor(random()*15)::int]
  END,
  CASE WHEN tool = 'ecosystem_search' THEN NULL ELSE fw END,
  CASE
    WHEN tool = 'resource' THEN NULL
    WHEN tool IN ('api_lookup', 'get_related') THEN
      CASE WHEN ts < now() - interval '7 days' THEN 0 ELSE 1 + floor(random() * 4)::int END
    ELSE (150 + (-ln(1 - random()) * 450))::int
  END,
  (800 + floor(random() * 9000))::int,
  CASE WHEN random() < 0.012 THEN 'upstream timeout' END
FROM (
  SELECT
    ts,
    (ARRAY['vue','vue','vue','vue','vue-router','vue-router','pinia','pinia','nuxt','nuxt','vueuse','vite','vitest','formkit','shadcn-vue','vitepress','vee-validate','pinia-colada','vue-flow','vue-devtools'])[1 + floor(random()*20)::int] AS fw,
    CASE
      WHEN r < 0.22 THEN 'resource'
      WHEN r < 0.50 THEN 'docs_search'
      WHEN r < 0.78 THEN 'api_lookup'
      WHEN r < 0.90 THEN 'get_related'
      ELSE 'ecosystem_search'
    END AS tool
  FROM (
    SELECT now() - make_interval(secs => random() * 30 * 86400) AS ts, random() AS r
    FROM generate_series(1, 14000)
  ) raw
  -- growth: later days get more events, weekends fewer
  WHERE random() < (0.35 + 0.65 * (1 - extract(epoch FROM (now() - ts)) / (30 * 86400)))
    AND (extract(isodow FROM ts) < 6 OR random() < 0.45)
) t;

SELECT count(*) AS seeded_events, min(timestamp)::date AS first_day, max(timestamp)::date AS last_day FROM usage_events;
