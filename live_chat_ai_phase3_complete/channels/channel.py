from __future__ import annotations
from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    channel_name = "unknown"

    @abstractmethod
    def send_message(self, recipient_id, text, metadata=None):
        raise NotImplementedError

    @abstractmethod
    def normalize_inbound(self, payload):
        raise NotImplementedError
