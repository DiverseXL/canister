"""Turn a ground() receipt into model-ready context text."""

from __future__ import annotations

from typing import Any


def build_context(receipt: dict[str, Any], store) -> list[dict[str, Any]]:
    """Attach document text to each final-context entry."""
    context = []
    for entry in receipt["final_context"]:
        context.append(
            {
                **entry,
                "text": store.get_text(entry["doc_id"]),
                "sha256": store.get_sha256(entry["doc_id"]),
            }
        )
    return context


def render_context(context: list[dict[str, Any]]) -> str:
    """Render the context as a single string, exactly as an agent would receive it."""
    blocks = []
    for entry in context:
        blocks.append(
            f"[{entry['doc_id']}] label={entry['label']} rank={entry['rank']}\n"
            f"{entry['text'].strip()}"
        )
    return "\n\n---\n\n".join(blocks)
