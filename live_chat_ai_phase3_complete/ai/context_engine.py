from __future__ import annotations

from database.database import get_messages

PERSONAS = {
    "general": "You are a helpful, precise, professional assistant.",
    "coding": "You are a senior software engineer. Give production-quality, correct technical guidance.",
    "business": "You are a practical business assistant focused on useful decisions.",
    "research": "You are a careful research assistant. Separate facts from uncertainty and do not invent sources.",
    "support": "You are a professional customer-support agent. Be concise, empathetic and solution-oriented.",
}


def build_messages(conversation_id: int, persona: str):
    messages = [
        {
            "role": "system",
            "content": PERSONAS.get(persona, PERSONAS["general"]),
        }
    ]

    # The user message has already been inserted into SQLite by app.py.
    # Therefore this history is the complete current context. Do NOT append
    # the current message again.
    for row in get_messages(conversation_id):
        role = row["role"]
        content = (row["content"] or "").strip()
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    return messages
