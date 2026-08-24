from __future__ import annotations

import threading

from database.database import create_conversation, get_conversation


class ChannelSessionStore:
    """
    Maps an external channel and sender to one internal conversation.

    Examples:
        web + web-user       -> conversation A
        telegram + 12345678  -> conversation B
        whatsapp + 880...    -> conversation C
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}

    def get_or_create(self, channel, sender_id, model, persona):
        key = (channel, str(sender_id))

        with self._lock:
            existing = self._sessions.get(key)
            if existing and get_conversation(existing):
                return existing

            cid = create_conversation(
                title=f"{channel.title()} — {sender_id}",
                model=model,
                persona=persona,
            )
            self._sessions[key] = cid
            return cid
