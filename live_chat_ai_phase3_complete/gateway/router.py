from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading

from ai.context_engine import build_messages
from database.database import create_conversation, get_conversation
from gateway.session_store import ChannelSessionStore


PERSONA_INFO = [
    {"id": "general", "name": "General Assistant"},
    {"id": "coding", "name": "Coding Expert"},
    {"id": "business", "name": "Business Assistant"},
    {"id": "research", "name": "Research Assistant"},
    {"id": "support", "name": "Customer Support"},
]


@dataclass
class InboundMessage:
    channel: str
    sender_id: str
    text: str
    sender_name: str | None = None
    metadata: dict = field(default_factory=dict)
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class MessageGateway:
    def __init__(self, ollama):
        self.ollama = ollama
        self.sessions = ChannelSessionStore()

    def personas(self):
        return PERSONA_INFO

    def inbound(self, channel, sender_id, text, sender_name=None, metadata=None):
        cid = self.sessions.get_or_create(
            channel=channel,
            sender_id=sender_id,
            model=self.ollama.default_model,
            persona="general",
        )
        return {
            "ok": True,
            "conversation_id": cid,
            "message": InboundMessage(
                channel=channel,
                sender_id=sender_id,
                text=text,
                sender_name=sender_name,
                metadata=metadata or {},
            ).__dict__,
        }

    def stream_reply(self, conversation_id, model, persona, cancel_event: threading.Event):
        if not get_conversation(conversation_id):
            yield {"type": "error", "error": "Conversation not found"}
            return

        yield {"type": "status", "data": {"stage": "thinking"}}

        messages = build_messages(conversation_id, persona)

        for item in self.ollama.stream_chat(
            messages=messages,
            model=model,
            cancel_event=cancel_event,
        ):
            yield item
            if item["type"] in {"done", "stopped", "error"}:
                return

        if cancel_event.is_set():
            yield {"type": "stopped"}
        else:
            yield {"type": "done"}
