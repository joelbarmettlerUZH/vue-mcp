"""Cost calculation for search providers."""

# Jina AI pricing (per 1M tokens) - https://jina.ai/pricing
JINA_EMBED_COST_PER_M_TOKENS = 0.02
JINA_RERANK_COST_PER_M_TOKENS = 0.02

# Context7 pricing: $10/seat for 5000 calls, $10/1000 overflow
CONTEXT7_COST_PER_QUERY = 0.002  # $10 / 5000 calls


def jina_cost(embed_tokens: int | None, rerank_tokens: int | None) -> float | None:
    """Calculate internal cost for a query using Jina APIs."""
    if embed_tokens is None and rerank_tokens is None:
        return None
    total = 0.0
    if embed_tokens is not None:
        total += embed_tokens * JINA_EMBED_COST_PER_M_TOKENS / 1_000_000
    if rerank_tokens is not None:
        total += rerank_tokens * JINA_RERANK_COST_PER_M_TOKENS / 1_000_000
    return total
