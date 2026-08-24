from __future__ import annotations

import os
import requests

from channels.channel import ChannelAdapter


class TelegramAdapter(ChannelAdapter):
    channel_name = "telegram"

    def __init__(self, bot_token=None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")

    def enabled(self):
        return bool(self.bot_token)

    def send_message(self, recipient_id, text, metadata=None):
        if not self.enabled():
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": recipient_id, "text": text},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def normalize_inbound(self, payload):
        message = payload.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}

        return {
            "channel": "telegram",
            "sender_id": str(chat.get("id", "")),
            "sender_name": " ".join(
                x for x in [sender.get("first_name"), sender.get("last_name")] if x
            ) or None,
            "message": message.get("text", ""),
            "metadata": {
                "telegram_message_id": message.get("message_id"),
                "chat_type": chat.get("type"),
            },
        }
