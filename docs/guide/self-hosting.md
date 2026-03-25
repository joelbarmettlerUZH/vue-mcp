# Self-Hosting

You can run your own instance of the Vue Docs MCP server. This gives you full control and works offline (after initial setup).

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **API keys** for:
  - [Jina AI](https://jina.ai/) (embeddings and reranking)
  - [Google Gemini](https://ai.google.dev/) (contextual enrichment and summarization during ingestion)
  - [Qdrant](https://qdrant.tech/) (vector database, cloud or self-hosted)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/joelbarmettlerUZH/vue-mcp.git
cd vue-mcp
make bootstrap    # Clones Vue docs + installs dependencies
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```ini
JINA_API_KEY=your-jina-api-key
GEMINI_API_KEY=your-gemini-api-key
QDRANT_URL=http://localhost:6333
DATABASE_URL=postgresql+psycopg://vue_mcp:vue_mcp@localhost:5432/vue_mcp
```

### 3. Run the ingestion pipeline

Parse the Vue documentation, generate embeddings, and index into Qdrant:

```bash
make ingest       # Incremental (skips unchanged files)
make ingest-full  # Full re-index from scratch
```

::: info
The first ingestion run will take a while as it embeds all documentation. Subsequent runs are incremental and much faster.
:::

### 4. Start the server

```bash
make serve
```

### 5. Connect your client

For local use with stdio transport:

```json
{
  "mcpServers": {
    "vue-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/vue-mcp", "vue-docs-server"]
    }
  }
}
```

See [MCP Clients](/clients/) for all client configurations.

## Docker Compose (Production)

For production deployments, use the Docker Compose stack:

### Architecture

```
Internet -> Traefik (:80/:443, TLS) -> MCP Server (:8000)
                                            |-- PostgreSQL
                                            |-- Qdrant
                                            '-- Ingestion (self-scheduling)
```

### Services

| Service | Purpose |
|---|---|
| **mcp-server** | FastMCP server (streamable HTTP) |
| **ingestion** | Self-scheduling pipeline (runs every 24h) |
| **postgres** | Shared data layer |
| **qdrant** | Vector database |
| **traefik** | Reverse proxy with TLS and rate limiting |

### Running

```bash
# Configure environment
cp .env.production.example .env.production
# Edit .env.production with your API keys and domain

# Build and start
make docker-build
make docker-up
```

### Environment Variables

For production, set these additional variables:

```ini
# Server transport
SERVER_TRANSPORT=streamable-http
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# PostgreSQL (required for production)
DATABASE_URL=postgresql+psycopg://vue_mcp:vue_mcp@postgres:5432/vue_mcp

# TLS (Traefik)
TLS_CERTRESOLVER=letsencrypt
ACME_EMAIL=your-email@example.com
DOMAIN=your-domain.com
```

### Hot Reload

When using PostgreSQL, the server automatically reloads data every 60 seconds. When ingestion writes new data, the server picks it up with zero downtime.

### Backup & Restore

```bash
scripts/backup.sh [backup_dir]              # pg_dump + Qdrant snapshot
scripts/restore.sh <dump.sql.gz> [snapshot]  # Restore from backup
```

Backups are rotated on a 7-day schedule.

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `JINA_API_KEY` | *required* | Jina AI API key |
| `GEMINI_API_KEY` | *required* | Google Gemini API key |
| `DATABASE_URL` | *required* | PostgreSQL connection string |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `DATA_PATH` | `./data` | Working directory for cloned docs |
| `SERVER_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `SERVER_HOST` | `0.0.0.0` | Server bind address |
| `SERVER_PORT` | `8000` | Server port |
| `MASK_ERROR_DETAILS` | `false` | Hide error traces in responses |
