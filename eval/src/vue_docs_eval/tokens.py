"""Token counting via tiktoken for accurate context size measurement."""

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding (GPT-4/Claude approximation)."""
    return len(_enc.encode(text))
