from __future__ import annotations

import json
from typing import Iterator
import requests


class OllamaClient:
    def __init__(self, base_url: str, default_model: str):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.connect_timeout = 10
        self.read_timeout = 900

    def health(self):
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=self.connect_timeout,
            )
            response.raise_for_status()
            return {"online": True, "models": response.json().get("models", [])}
        except Exception as exc:
            return {"online": False, "error": str(exc)}

    def list_models(self):
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=self.connect_timeout,
            )
            response.raise_for_status()
            models = response.json().get("models", [])
            return {
                "models": [
                    {
                        "name": m.get("name"),
                        "size": m.get("size"),
                        "modified_at": m.get("modified_at"),
                    }
                    for m in models
                ]
            }
        except Exception as exc:
            return {"models": [], "error": str(exc)}

    def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        cancel_event=None,
    ) -> Iterator[dict]:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": True,
        }

        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=(self.connect_timeout, self.read_timeout),
            ) as response:
                response.raise_for_status()

                for raw in response.iter_lines(decode_unicode=True):
                    if cancel_event is not None and cancel_event.is_set():
                        yield {"type": "stopped"}
                        return

                    if not raw:
                        continue

                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("error"):
                        yield {"type": "error", "error": obj["error"]}
                        return

                    message = obj.get("message") or {}
                    content = message.get("content")
                    if content:
                        yield {"type": "token", "text": content}

                    # This is Ollama's authoritative terminal signal.
                    if obj.get("done") is True:
                        yield {
                            "type": "done",
                            "stats": {
                                "total_duration": obj.get("total_duration"),
                                "load_duration": obj.get("load_duration"),
                                "prompt_eval_count": obj.get("prompt_eval_count"),
                                "eval_count": obj.get("eval_count"),
                                "eval_duration": obj.get("eval_duration"),
                            },
                        }
                        return

                # Server closed the stream cleanly without done=true.
                if cancel_event is not None and cancel_event.is_set():
                    yield {"type": "stopped"}
                else:
                    yield {"type": "done", "implicit": True}

        except requests.RequestException as exc:
            if cancel_event is not None and cancel_event.is_set():
                yield {"type": "stopped"}
            else:
                yield {"type": "error", "error": str(exc)}
