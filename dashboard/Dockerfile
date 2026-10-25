# Usage dashboard: Bun API + prebuilt Vue page. Build context is this directory.
FROM oven/bun:1.4.3 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY web ./web
RUN bun run build

FROM oven/bun:1.4.3-slim AS runtime
# Pick up Debian security fixes published since the base image was built.
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server ./server
COPY --from=build /app/web/dist ./web/dist
ENV PORT=3100
EXPOSE 3100
USER bun
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["bun", "-e", "const r = await fetch('http://127.0.0.1:' + (process.env.PORT ?? 3100) + '/healthz'); process.exit(r.ok ? 0 : 1)"]
CMD ["bun", "server/index.ts"]
