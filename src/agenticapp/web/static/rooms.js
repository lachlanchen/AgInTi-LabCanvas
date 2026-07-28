"use strict";

const app = document.querySelector("[data-testid='rooms-app']");
const roomList = document.getElementById("roomList");
const roomTitle = document.getElementById("roomTitle");
const roomStatus = document.getElementById("roomStatus");
const messageStream = document.getElementById("messageStream");
const emptyState = document.getElementById("emptyState");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const modelSelect = document.getElementById("modelSelect");
const effortSelect = document.getElementById("effortSelect");
const artifactList = document.getElementById("artifactList");
const toast = document.getElementById("toast");
const createRoomDialog = document.getElementById("createRoomDialog");
const inviteDialog = document.getElementById("inviteDialog");
const identityDialog = document.getElementById("identityDialog");

const params = new URLSearchParams(window.location.search);
const state = {
  roomId: params.get("room") || "labagent",
  roomName: "LabAgent",
  invite: params.get("invite") || "",
  ownerToken: params.get("token") || sessionStorage.getItem("labcanvas.rooms.ownerToken") || "",
  accessRole: params.get("invite") ? "participant" : "owner",
  cursor: 0,
  messages: new Map(),
  rooms: [],
  pendingTasks: new Set(),
  polling: false,
  pollTimer: 0,
  sending: false,
  displayName: localStorage.getItem("labcanvas.rooms.displayName") || "",
};

if (state.ownerToken) sessionStorage.setItem("labcanvas.rooms.ownerToken", state.ownerToken);
if (state.invite) sessionStorage.setItem(`labcanvas.rooms.invite.${state.roomId}`, state.invite);
if (!state.invite) state.invite = sessionStorage.getItem(`labcanvas.rooms.invite.${state.roomId}`) || "";
if (state.invite) state.accessRole = "participant";

function credentialHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.ownerToken) headers.Authorization = `Bearer ${state.ownerToken}`;
  if (state.invite) headers["X-LabCanvas-Room-Invite"] = state.invite;
  return headers;
}

function credentialUrl(path) {
  const url = new URL(path, window.location.origin);
  if (state.invite) url.searchParams.set("invite", state.invite);
  else if (state.ownerToken) url.searchParams.set("token", state.ownerToken);
  return url.toString();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: credentialHeaders(options.headers || {}),
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) { payload = {}; }
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function setStatus(text, stateName = "ready") {
  roomStatus.textContent = text;
  roomStatus.dataset.state = stateName;
}

function showToast(message) {
  toast.textContent = message;
  toast.dataset.visible = "true";
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.dataset.visible = "false"; }, 2600);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(date);
}

function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => Array.from(part)[0]).join("").toUpperCase() || "?";
}

function renderRooms() {
  roomList.replaceChildren();
  for (const room of state.rooms) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "room-item";
    button.dataset.roomId = room.id;
    if (room.id === state.roomId) button.setAttribute("aria-current", "page");

    const mark = document.createElement("span");
    mark.className = "room-mark";
    mark.textContent = initials(room.name).slice(0, 1);
    const name = document.createElement("span");
    name.className = "room-name";
    name.textContent = room.name;
    const count = document.createElement("span");
    count.className = "room-count";
    count.textContent = room.message_count ? String(room.message_count) : "";
    button.append(mark, name, count);
    button.addEventListener("click", () => selectRoom(room.id, room.name));
    roomList.append(button);
  }
}

function artifactLink(artifact) {
  const link = document.createElement("a");
  link.href = credentialUrl(artifact.url);
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = artifact.title || "Artifact";
  return link;
}

function appendMessage(message) {
  if (state.messages.has(message.id)) return;
  state.messages.set(message.id, message);
  if (message.role === "assistant" && message.task_id) {
    state.pendingTasks.delete(message.task_id);
  }
  emptyState.hidden = true;

  const item = document.createElement("article");
  item.className = "message";
  item.dataset.role = message.role;
  item.dataset.messageId = String(message.id);
  item.dataset.testid = `room-message-${message.role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = message.role === "assistant" ? "LC" : initials(message.sender_name);
  const body = document.createElement("div");
  body.className = "message-body";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const sender = document.createElement("span");
  sender.className = "message-sender";
  sender.textContent = message.sender_name;
  const time = document.createElement("time");
  time.className = "message-time";
  time.dateTime = message.created_at;
  time.textContent = formatTime(message.created_at);
  const text = document.createElement("div");
  text.className = "message-text";
  text.textContent = message.content;
  meta.append(sender, time);
  body.append(meta, text);

  if (Array.isArray(message.artifacts) && message.artifacts.length) {
    const links = document.createElement("div");
    links.className = "message-artifacts";
    for (const artifact of message.artifacts) links.append(artifactLink(artifact));
    body.append(links);
  }
  item.append(avatar, body);
  messageStream.append(item);
}

function renderArtifacts() {
  const artifacts = Array.from(state.messages.values()).flatMap((message) => message.artifacts || []).reverse();
  artifactList.replaceChildren();
  if (!artifacts.length) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No artifacts yet.";
    artifactList.append(empty);
    return;
  }
  for (const artifact of artifacts) {
    const link = artifactLink(artifact);
    link.className = "artifact-item";
    link.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = artifact.title || "Artifact";
    const meta = document.createElement("span");
    meta.textContent = [artifact.kind, artifact.mime].filter(Boolean).join(" · ") || "File";
    link.append(title, meta);
    artifactList.append(link);
  }
}

async function loadRooms() {
  if (state.accessRole === "participant") {
    state.rooms = [{ id: state.roomId, name: state.roomName, message_count: 0 }];
    renderRooms();
    return;
  }
  const payload = await api("/api/rooms");
  state.rooms = payload.rooms || [];
  const selected = state.rooms.find((room) => room.id === state.roomId) || state.rooms[0];
  if (selected) {
    state.roomId = selected.id;
    state.roomName = selected.name;
  }
  renderRooms();
}

async function pollMessages({ reset = false } = {}) {
  if (state.polling) return;
  state.polling = true;
  try {
    if (reset) {
      state.cursor = 0;
      state.messages.clear();
      messageStream.querySelectorAll(".message").forEach((node) => node.remove());
      emptyState.hidden = false;
    }
    const nearBottom = messageStream.scrollHeight - messageStream.scrollTop - messageStream.clientHeight < 100;
    const query = new URLSearchParams({ after: String(state.cursor), limit: "200" });
    const payload = await api(`/api/rooms/${encodeURIComponent(state.roomId)}/messages?${query}`);
    if (payload.room) {
      state.roomName = payload.room.name;
      roomTitle.textContent = payload.room.name;
    }
    for (const message of payload.messages || []) appendMessage(message);
    state.cursor = Math.max(state.cursor, Number(payload.cursor || 0));
    renderArtifacts();
    if (nearBottom && (payload.messages || []).length) messageStream.scrollTop = messageStream.scrollHeight;
    setStatus(state.pendingTasks.size ? "Agent working" : state.accessRole === "participant" ? "Guest · read only" : "Ready", state.pendingTasks.size ? "working" : "ready");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.polling = false;
  }
}

function schedulePolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => pollMessages(), 2000);
}

async function selectRoom(roomId, name) {
  if (state.accessRole === "participant" && roomId !== state.roomId) return;
  state.roomId = roomId;
  state.roomName = name;
  roomTitle.textContent = name;
  const next = new URL(window.location.href);
  next.searchParams.set("room", roomId);
  if (!state.invite) next.searchParams.delete("invite");
  history.replaceState({}, "", next);
  renderRooms();
  app.dataset.sidebarOpen = "false";
  await pollMessages({ reset: true });
}

async function sendMessage(event) {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || state.sending) return;
  if (!state.displayName) {
    identityDialog.showModal();
    return;
  }
  state.sending = true;
  sendButton.disabled = true;
  setStatus("Sending", "working");
  try {
    const payload = await api(`/api/rooms/${encodeURIComponent(state.roomId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        sender_id: state.accessRole === "participant" ? `guest-${state.displayName}` : "local-owner",
        sender_name: state.displayName,
        model: modelSelect.value,
        effort: effortSelect.value,
      }),
    });
    messageInput.value = "";
    resizeComposer();
    if (payload.task && payload.task.id) state.pendingTasks.add(payload.task.id);
    await pollMessages();
  } catch (error) {
    setStatus(error.message, "error");
    showToast(error.message);
  } finally {
    state.sending = false;
    sendButton.disabled = false;
    messageInput.focus();
  }
}

function resizeComposer() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(180, Math.max(54, messageInput.scrollHeight))}px`;
}

async function createRoom(event) {
  event.preventDefault();
  const name = document.getElementById("roomNameInput").value.trim();
  if (!name) return;
  try {
    const payload = await api("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    createRoomDialog.close();
    await loadRooms();
    await selectRoom(payload.room.id, payload.room.name);
  } catch (error) { showToast(error.message); }
}

async function createInvite() {
  const button = document.getElementById("createInviteButton");
  button.disabled = true;
  try {
    const payload = await api(`/api/rooms/${encodeURIComponent(state.roomId)}/invites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: document.getElementById("inviteLabel").value,
        expires_hours: Number(document.getElementById("inviteLifetime").value),
      }),
    });
    const url = new URL("/rooms", window.location.origin);
    url.searchParams.set("room", state.roomId);
    url.searchParams.set("invite", payload.invite.token);
    document.getElementById("inviteUrl").value = url.toString();
    document.getElementById("inviteExpiry").textContent = `Expires ${new Date(payload.invite.expires_at).toLocaleString()}`;
    document.getElementById("inviteCreateView").hidden = true;
    document.getElementById("inviteResultView").hidden = false;
  } catch (error) { showToast(error.message); }
  finally { button.disabled = false; }
}

document.getElementById("createRoomButton").addEventListener("click", () => createRoomDialog.showModal());
document.getElementById("createRoomCancel").addEventListener("click", () => createRoomDialog.close());
document.getElementById("createRoomForm").addEventListener("submit", createRoom);
document.getElementById("inviteButton").addEventListener("click", () => {
  document.getElementById("inviteRoomName").textContent = state.roomName;
  document.getElementById("inviteCreateView").hidden = false;
  document.getElementById("inviteResultView").hidden = true;
  inviteDialog.showModal();
});
document.getElementById("createInviteButton").addEventListener("click", createInvite);
document.getElementById("copyInviteButton").addEventListener("click", async () => {
  const value = document.getElementById("inviteUrl").value;
  await navigator.clipboard.writeText(value);
  showToast("Invite link copied");
});
document.getElementById("identityForm").addEventListener("submit", (event) => {
  event.preventDefault();
  state.displayName = document.getElementById("displayNameInput").value.trim() || "Guest";
  localStorage.setItem("labcanvas.rooms.displayName", state.displayName);
  identityDialog.close();
  messageInput.focus();
});
document.getElementById("refreshButton").addEventListener("click", () => pollMessages({ reset: true }));
document.getElementById("artifactButton").addEventListener("click", () => { app.dataset.artifactsOpen = "true"; });
document.getElementById("artifactClose").addEventListener("click", () => { app.dataset.artifactsOpen = "false"; });
document.getElementById("sidebarOpen").addEventListener("click", () => { app.dataset.sidebarOpen = "true"; });
document.getElementById("sidebarClose").addEventListener("click", () => { app.dataset.sidebarOpen = "false"; });
document.getElementById("pageScrim").addEventListener("click", () => {
  app.dataset.sidebarOpen = "false";
  app.dataset.artifactsOpen = "false";
});
messageInput.addEventListener("input", resizeComposer);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
composer.addEventListener("submit", sendMessage);

async function start() {
  app.dataset.accessRole = state.accessRole;
  if (state.accessRole === "participant") {
    document.getElementById("createRoomButton").hidden = true;
    document.getElementById("inviteButton").hidden = true;
    document.getElementById("agentControls").hidden = true;
    if (!state.displayName) identityDialog.showModal();
  } else if (!state.displayName) {
    state.displayName = "Owner";
    localStorage.setItem("labcanvas.rooms.displayName", state.displayName);
  }
  try {
    await loadRooms();
    roomTitle.textContent = state.roomName;
    await pollMessages({ reset: true });
    schedulePolling();
  } catch (error) {
    setStatus(error.message, "error");
  }
  messageInput.focus();
}

start();
