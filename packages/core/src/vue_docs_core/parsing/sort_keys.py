"""Sidebar config parsing and global sort key computation.

Parses the VitePress ``config.ts`` sidebar definition to derive a global
ordering for every documentation page.  Files not present in the sidebar
receive a fallback alphabetical sort key that sorts after all sidebar entries.
"""

import re
from pathlib import Path

_SECTION_RE = re.compile(r"'(\/[\w-]+\/?)'\s*:\s*\[")
_ITEMS_RE = re.compile(r"items\s*:\s*\[")
_LINK_RE = re.compile(r"link:\s*'(/[^']+)'")


def parse_sidebar_config(config_path: Path) -> dict[str, str]:
    """Parse the VitePress config.ts and return ``{page_path: sort_key}``.

    Sort keys have the format ``{section:02d}_{group:02d}_{item:02d}``
    where *section* is the sidebar key index (guide=0, api=1, …),
    *group* is the group index within the sidebar section, and *item*
    is the item position within the group.

    Page paths are normalized: no leading slash, no ``.html`` suffix,
    no trailing slash.
    """
    raw = config_path.read_text(encoding="utf-8")
    result: dict[str, str] = {}

    for section_idx, section_match in enumerate(_SECTION_RE.finditer(raw)):
        start = section_match.end()

        # Find the matching closing bracket for this section
        depth = 1
        pos = start
        while depth > 0 and pos < len(raw):
            if raw[pos] == "[":
                depth += 1
            elif raw[pos] == "]":
                depth -= 1
            pos += 1

        section_text = raw[start : pos - 1]

        group_idx = -1
        item_idx = 0

        for line in section_text.split("\n"):
            if _ITEMS_RE.search(line):
                group_idx += 1
                item_idx = 0

            lm = _LINK_RE.search(line)
            if lm:
                path = lm.group(1).lstrip("/").rstrip("/")
                path = re.sub(r"\.html$", "", path)
                path = path.split("#")[0]  # strip anchors

                if path:
                    sort_key = f"{section_idx:02d}_{max(0, group_idx):02d}_{item_idx:02d}"
                    result[path] = sort_key
                    item_idx += 1

    return result


def compute_sort_key(file_path: str, sidebar_map: dict[str, str]) -> str:
    """Return the sort key for a documentation file.

    Files not in the sidebar get a ``99_`` prefixed fallback that sorts
    after all sidebar-listed pages.
    """
    # Normalize: strip .md extension
    normalized = re.sub(r"\.md$", "", file_path)

    if normalized in sidebar_map:
        return sidebar_map[normalized]

    # Fallback: 99_{folder}/{filename} for alphabetical ordering
    return f"99_{normalized}"
