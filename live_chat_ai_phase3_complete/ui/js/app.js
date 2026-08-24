(() => {
  "use strict";

  const state = {
    conversationId: null,
    conversations: [],
    model: "llama3.1:8b",
    persona: "general",
    generating: false,
    requestId: null,
    abortController: null,
    generationSerial: 0,
  };

  const $ = id => document.getElementById(id);

  const els = {
    newChat: $("newChat"),
    conversationList: $("conversationList"),
    messages: $("messages"),
    input: $("input"),
    send: $("send"),
    stop: $("stop"),
    model: $("model"),
    persona: $("persona"),
    title: $("chatTitle"),
    status: $("status"),
    healthDot: $("healthDot"),
    healthText: $("healthText"),
  };

  function setStatus(text) {
    els.status.textContent = text;
  }

  function setGenerating(value) {
    state.generating = value;
    els.send.disabled = value;
    els.stop.disabled = !value;
    els.input.disabled = false;
    els.newChat.disabled = false;
    els.model.disabled = false;
    els.persona.disabled = false;
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function addMessage(role, text = "") {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;

    const inner = document.createElement("div");
    inner.className = "bubble";

    const roleLabel = document.createElement("div");
    roleLabel.className = "role";
    roleLabel.textContent = role === "user" ? "YOU" : "AI";

    const content = document.createElement("div");
    content.className = "content";
    content.textContent = text;

    inner.appendChild(roleLabel);
    inner.appendChild(content);
    wrapper.appendChild(inner);
    els.messages.appendChild(wrapper);

    els.messages.scrollTop = els.messages.scrollHeight;
    return content;
  }

  function clearMessages() {
    els.messages.innerHTML = "";
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function loadModels() {
    const data = await jsonFetch("/api/models");
    els.model.innerHTML = "";

    for (const model of data.models || []) {
      const option = document.createElement("option");
      option.value = model.name;
      option.textContent = model.name;
      els.model.appendChild(option);
    }

    if ([...els.model.options].some(o => o.value === state.model)) {
      els.model.value = state.model;
    } else if (els.model.options.length) {
      state.model = els.model.options[0].value;
      els.model.value = state.model;
    }
  }

  async function loadPersonas() {
    const data = await jsonFetch("/api/personas");
    els.persona.innerHTML = "";

    for (const persona of data) {
      const option = document.createElement("option");
      option.value = persona.id;
      option.textContent = persona.name;
      els.persona.appendChild(option);
    }

    els.persona.value = state.persona;
  }

  async function checkHealth() {
    try {
      const data = await jsonFetch("/api/ollama/health");
      if (data.online) {
        els.healthDot.className = "dot ok";
        els.healthText.textContent = "Ollama online";
      } else {
        throw new Error(data.error || "Offline");
      }
    } catch (err) {
      els.healthDot.className = "dot bad";
      els.healthText.textContent = "Ollama offline";
    }
  }

  async function loadConversations() {
    const data = await jsonFetch("/api/conversations");
    state.conversations = data.conversations || [];
    renderConversationList();

    if (!state.conversationId && state.conversations.length) {
      await selectConversation(state.conversations[0].id);
    }
  }

  function renderConversationList() {
    els.conversationList.innerHTML = "";

    for (const conversation of state.conversations) {
      const item = document.createElement("div");
      item.className = "conv" + (
        Number(conversation.id) === Number(state.conversationId) ? " active" : ""
      );

      const title = document.createElement("div");
      title.className = "conv-title";
      title.textContent = conversation.title || "New Chat";

      const meta = document.createElement("div");
      meta.className = "conv-meta";
      meta.textContent = `${conversation.model} · ${conversation.persona}`;

      item.append(title, meta);
      item.addEventListener("click", () => selectConversation(conversation.id));
      els.conversationList.appendChild(item);
    }
  }

  async function createNewChat() {
    // Navigation is intentionally independent of generation state.
    if (state.generating) {
      await stopGeneration();
    }

    const data = await jsonFetch("/api/conversations", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        model: state.model,
        persona: state.persona,
      }),
    });

    state.conversationId = data.conversation.id;
    state.model = data.conversation.model;
    state.persona = data.conversation.persona;

    els.model.value = state.model;
    els.persona.value = state.persona;
    els.title.textContent = data.conversation.title;

    clearMessages();
    setStatus("Ready");
    renderConversationList();
    await loadConversations();
    els.input.focus();
  }

  async function selectConversation(id) {
    if (state.generating) {
      await stopGeneration();
    }

    const data = await jsonFetch(`/api/conversations/${id}`);

    state.conversationId = data.id;
    state.model = data.model;
    state.persona = data.persona;

    els.model.value = state.model;
    els.persona.value = state.persona;
    els.title.textContent = data.title || "New Chat";

    clearMessages();

    for (const message of data.messages || []) {
      if (message.role === "user" || message.role === "assistant") {
        addMessage(message.role, message.content);
      }
    }

    setStatus("Ready");
    renderConversationList();
    els.input.focus();
  }

  async function stopGeneration() {
    if (!state.generating || !state.requestId) {
      setGenerating(false);
      return;
    }

    const requestId = state.requestId;

    try {
      await jsonFetch("/api/chat/stop", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({request_id: requestId}),
      });
    } catch (_) {
      // The stream may already have closed. UI still must be released.
    }

    if (state.abortController) {
      state.abortController.abort();
    }

    setGenerating(false);
    state.requestId = null;
    state.abortController = null;
    setStatus("Stopped");
  }

  async function sendMessage() {
    if (state.generating) return;

    const text = els.input.value.trim();
    if (!text) return;

    if (!state.conversationId) {
      await createNewChat();
    }

    const requestId = crypto.randomUUID();
    const serial = ++state.generationSerial;

    state.requestId = requestId;
    state.abortController = new AbortController();

    els.input.value = "";
    addMessage("user", text);
    const assistantContent = addMessage("assistant", "");

    setGenerating(true);
    setStatus("Generating…");

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          conversation_id: state.conversationId,
          message: text,
          model: state.model,
          persona: state.persona,
          request_id: requestId,
        }),
        signal: state.abortController.signal,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      if (!response.body) throw new Error("Streaming response is unavailable.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const {value, done} = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, {stream: true});

        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";

        for (const chunk of chunks) {
          handleSseChunk(chunk, assistantContent, requestId);
        }
      }

      // Process any final SSE frame.
      if (buffer.trim()) {
        handleSseChunk(buffer, assistantContent, requestId);
      }

      // Defensive frontend release. The backend also sends done/closed.
      if (serial === state.generationSerial && state.requestId === requestId) {
        setGenerating(false);
        state.requestId = null;
        state.abortController = null;
        setStatus("Ready");
        await loadConversations();
      }

    } catch (err) {
      if (err.name === "AbortError") {
        return;
      }

      if (serial === state.generationSerial) {
        setStatus("Error");
        setGenerating(false);
        state.requestId = null;
        state.abortController = null;
        if (!assistantContent.textContent) {
          assistantContent.textContent = `Error: ${err.message}`;
        }
      }
    }
  }

  function handleSseChunk(chunk, assistantContent, requestId) {
    const lines = chunk.split("\n");
    let event = "message";
    let data = "";

    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data += line.slice(5).trim();
    }

    if (!data) return;

    let payload;
    try {
      payload = JSON.parse(data);
    } catch (_) {
      return;
    }

    if (payload.request_id && payload.request_id !== requestId) {
      return;
    }

    if (event === "token") {
      assistantContent.textContent += payload.text || "";
      els.messages.scrollTop = els.messages.scrollHeight;
      return;
    }

    if (event === "status") {
      setStatus(payload.stage === "thinking" ? "Thinking…" : "Generating…");
      return;
    }

    if (event === "done") {
      setGenerating(false);
      state.requestId = null;
      state.abortController = null;
      setStatus("Ready");
      loadConversations().catch(console.error);
      return;
    }

    if (event === "stopped") {
      setGenerating(false);
      state.requestId = null;
      state.abortController = null;
      setStatus("Stopped");
      loadConversations().catch(console.error);
      return;
    }

    if (event === "error") {
      setGenerating(false);
      state.requestId = null;
      state.abortController = null;
      setStatus("Error");
      if (!assistantContent.textContent) {
        assistantContent.textContent = `Error: ${payload.error || "Unknown error"}`;
      }
      return;
    }

    if (event === "closed") {
      // Do not rely only on this event, but always release the UI on closure.
      if (state.requestId === requestId) {
        setGenerating(false);
        state.requestId = null;
        state.abortController = null;
        if (state.status !== "Error") setStatus("Ready");
      }
    }
  }

  els.newChat.addEventListener("click", createNewChat);

  els.send.addEventListener("click", sendMessage);
  els.stop.addEventListener("click", stopGeneration);

  els.input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  els.model.addEventListener("change", async () => {
    state.model = els.model.value;
    if (state.conversationId) {
      await jsonFetch(`/api/conversations/${state.conversationId}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({model: state.model}),
      });
      await loadConversations();
    }
  });

  els.persona.addEventListener("change", async () => {
    state.persona = els.persona.value;
    if (state.conversationId) {
      await jsonFetch(`/api/conversations/${state.conversationId}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({persona: state.persona}),
      });
      await loadConversations();
    }
  });

  async function boot() {
    try {
      await Promise.all([loadModels(), loadPersonas(), checkHealth()]);
      await loadConversations();

      if (!state.conversationId) {
        await createNewChat();
      }

      els.input.focus();
    } catch (err) {
      setStatus(`Startup error: ${err.message}`);
    }
  }

  boot();
})();
