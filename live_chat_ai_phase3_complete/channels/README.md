# Channel adapters

Phase 3 establishes the external-message abstraction.

Current adapter:
- TelegramAdapter

Not connected automatically yet. Configure a bot token and add webhook/polling
or another transport layer in the next integration phase.

The important contract is:

inbound channel message
    -> normalize_inbound()
    -> MessageGateway
    -> internal conversation
    -> Ollama
    -> channel send_message()
