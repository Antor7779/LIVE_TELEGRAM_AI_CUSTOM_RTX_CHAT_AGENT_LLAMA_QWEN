from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from ai.ollama_client import OllamaClient
from database.database import (
    create_conversation, delete_conversation, get_conversation,
    get_conversations, get_messages, init_db, save_message,
    touch_conversation, update_conversation
)
from gateway.router import MessageGateway

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder="ui/templates", static_folder="ui", static_url_path="/ui")

init_db()

ollama = OllamaClient(
    base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
    default_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
)
gateway = MessageGateway(ollama)

_active = {}
_active_lock = threading.Lock()


def register_request(request_id: str):
    event = threading.Event()
    with _active_lock:
        _active[request_id] = event
    return event


def remove_request(request_id: str):
    with _active_lock:
        _active.pop(request_id, None)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/models")
def api_models():
    return jsonify(ollama.list_models())


@app.get("/api/personas")
def api_personas():
    return jsonify(gateway.personas())


@app.get("/api/ollama/health")
def api_health():
    return jsonify(ollama.health())


@app.get("/api/conversations")
def api_conversations():
    return jsonify({"conversations": get_conversations()})


@app.post("/api/conversations")
def api_create_conversation():
    data = request.get_json(silent=True) or {}
    cid = create_conversation(
        title=data.get("title") or "New Chat",
        model=data.get("model") or ollama.default_model,
        persona=data.get("persona") or "general",
    )
    return jsonify({"conversation": get_conversation(cid)}), 201


@app.get("/api/conversations/<int:conversation_id>")
def api_get_conversation(conversation_id):
    conversation = get_conversation(conversation_id)
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404
    conversation["messages"] = get_messages(conversation_id)
    return jsonify(conversation)


@app.patch("/api/conversations/<int:conversation_id>")
def api_update_conversation(conversation_id):
    data = request.get_json(silent=True) or {}
    update_conversation(
        conversation_id,
        title=data.get("title"),
        model=data.get("model"),
        persona=data.get("persona"),
    )
    return jsonify({"conversation": get_conversation(conversation_id)})


@app.delete("/api/conversations/<int:conversation_id>")
def api_delete_conversation(conversation_id):
    delete_conversation(conversation_id)
    return jsonify({"ok": True})


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}

    conversation_id = data.get("conversation_id")
    text = (data.get("message") or "").strip()
    model = data.get("model")
    persona = data.get("persona")
    request_id = data.get("request_id") or str(uuid.uuid4())

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    if not text:
        return jsonify({"error": "message is required"}), 400

    conversation = get_conversation(int(conversation_id))
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    model = model or conversation["model"] or ollama.default_model
    persona = persona or conversation["persona"] or "general"

    # Save exactly once. context_engine reads the DB and therefore must not
    # append this message a second time.
    save_message(conversation_id, "user", text, model)
    touch_conversation(conversation_id)

    cancel_event = register_request(request_id)

    def stream():
        accumulated = []
        terminal = False
        assistant_saved = False

        def save_partial():
            nonlocal assistant_saved
            content = "".join(accumulated).strip()
            if content and not assistant_saved:
                save_message(conversation_id, "assistant", content, model)
                touch_conversation(conversation_id)
                assistant_saved = True
            return content

        try:
            yield sse("meta", {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "status": "running",
            })

            for item in gateway.stream_reply(
                conversation_id=int(conversation_id),
                model=model,
                persona=persona,
                cancel_event=cancel_event,
            ):
                kind = item["type"]

                if kind == "token":
                    accumulated.append(item["text"])
                    yield sse("token", {"text": item["text"]})

                elif kind == "status":
                    yield sse("status", item["data"])

                elif kind == "done":
                    terminal = True
                    content = save_partial()
                    yield sse("done", {
                        "status": "completed",
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "text": content,
                        "stats": item.get("stats", {}),
                    })

                elif kind == "stopped":
                    terminal = True
                    content = save_partial()
                    yield sse("stopped", {
                        "status": "stopped",
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "text": content,
                    })

                elif kind == "error":
                    terminal = True
                    yield sse("error", {
                        "request_id": request_id,
                        "error": item["error"],
                    })

            # Critical fix: an unexpected clean EOF can never leave the browser
            # stuck in "generating". Treat it as completion unless cancelled.
            if not terminal:
                if cancel_event.is_set():
                    content = save_partial()
                    yield sse("stopped", {
                        "status": "stopped",
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "text": content,
                    })
                else:
                    content = save_partial()
                    yield sse("done", {
                        "status": "completed",
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "text": content,
                        "implicit": True,
                    })

        except GeneratorExit:
            cancel_event.set()
            raise
        except Exception as exc:
            yield sse("error", {
                "request_id": request_id,
                "error": str(exc),
            })
        finally:
            remove_request(request_id)
            yield sse("closed", {"request_id": request_id})

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/chat/stop")
def api_stop():
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id")

    if not request_id:
        return jsonify({"error": "request_id is required"}), 400

    with _active_lock:
        event = _active.get(request_id)

    if event:
        event.set()
        return jsonify({"ok": True, "status": "stopping", "request_id": request_id})

    return jsonify({"ok": True, "status": "not_running", "request_id": request_id})


@app.post("/api/gateway/message")
def api_gateway_message():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"error": "message is required"}), 400

    return jsonify(gateway.inbound(
        channel=data.get("channel", "web"),
        sender_id=str(data.get("sender_id", "web-user")),
        sender_name=data.get("sender_name"),
        text=text,
        metadata=data.get("metadata") or {},
    ))


def sse(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    print("=" * 72)
    print("LIVE CHAT AI — PHASE 3")
    print("=" * 72)
    print("Web:     http://127.0.0.1:7860")
    print("Ollama:  " + ollama.base_url)
    print("Features: streaming, clean completion, stop, gateway, conversations")
    print("=" * 72)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "7860")),
            debug=False, threaded=True)
