# Live Chat AI — Phase 3

## Architecture

Web UI / future external channels
        |
        v
Message Gateway
        |
        v
Conversation + Context Engine
        |
        v
Ollama
        |
        v
Streaming response
        |
        v
Channel adapter

## Phase 3 fixes

1. Ollama's `done: true` event is treated as the authoritative completion signal.
2. Unexpected clean EOF is converted into a terminal `done` event.
3. The backend always removes the active request in `finally`.
4. The frontend always releases its generating state on done/stopped/error/closed.
5. New Chat is allowed during generation; it stops the current request first.
6. Conversation switching is allowed during generation; it stops the current request first.
7. The current user message is stored once and is not duplicated in the Ollama context.
8. Request IDs prevent an old stream from changing a newly selected conversation.
9. A channel/session abstraction is ready for Telegram and WhatsApp integrations.
10. SQLite remains the local persistence layer.

## Install

From E:\AI_Script_writer\live_chat_ai:

    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt

If your existing environment already has Flask and requests, this is safe.

## Run

    python .\app.py

Open:

    http://127.0.0.1:7860

## Existing database

This code does not require deleting your chat database. The schema uses
CREATE TABLE IF NOT EXISTS and is compatible with the Phase 1 conversation
tables. If you have an older database with an incompatible schema, back it up
before changing it.

## Test

1. Send a normal message.
2. Wait for the complete answer.
3. Confirm the status returns to Ready without pressing Stop.
4. Send another message.
5. Start a long response and click Stop.
6. Click New Chat while generation is active.
7. Switch back to the previous conversation.
8. Send a message in the new conversation.
9. Switch between conversations while generation is active.

## Phase 3 channel direction

The gateway is deliberately channel-neutral.

Future:

Telegram -> TelegramAdapter -> MessageGateway -> Ollama
WhatsApp -> WhatsAppAdapter -> MessageGateway -> Ollama
Web      -> Web UI         -> MessageGateway -> Ollama

Do not put Telegram/WhatsApp-specific logic inside the Ollama client.
