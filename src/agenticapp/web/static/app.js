let spec = null;
let rendering = false;

const messages = document.getElementById("messages");
const chatStatus = document.getElementById("chatStatus");
const renderStatus = document.getElementById("renderStatus");
const previewImage = document.getElementById("previewImage");
const emptyPreview = document.getElementById("emptyPreview");
const specEditor = document.getElementById("specEditor");
const specMeta = document.getElementById("specMeta");
const titleInput = document.getElementById("titleInput");
const slugInput = document.getElementById("slugInput");
const pngLink = document.getElementById("pngLink");
const blendLink = document.getElementById("blendLink");
const specLink = document.getElementById("specLink");

init();

async function init() {
  const response = await fetch("/api/spec");
  const data = await response.json();
  spec = data.spec;
  syncSpecView();
  if (data.preview_url) {
    showPreview(data.preview_url);
  }
  addMessage("assistant", "Scene loaded. Ask for components, colors, labels, or a paper setup.");
}

document.getElementById("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("messageInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("user", text);
  chatStatus.textContent = "Thinking";
  try {
    const data = await postJson("/api/chat", { message: text, spec });
    if (!data.ok) throw new Error(data.error || "Chat failed");
    spec = data.spec;
    syncSpecView();
    addMessage("assistant", data.reply);
  } catch (error) {
    addMessage("assistant", error.message);
  } finally {
    chatStatus.textContent = "Ready";
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("messageInput").value = button.dataset.prompt;
    document.getElementById("chatForm").requestSubmit();
  });
});

document.getElementById("renderBtn").addEventListener("click", renderScene);
document.getElementById("dryRunBtn").addEventListener("click", dryRunScene);
document.getElementById("templateBtn").addEventListener("click", init);

document.getElementById("applySpecBtn").addEventListener("click", () => {
  try {
    spec = JSON.parse(specEditor.value);
    syncSpecView();
    addMessage("assistant", "Scene JSON applied.");
  } catch (error) {
    addMessage("assistant", `JSON error: ${error.message}`);
  }
});

titleInput.addEventListener("change", () => {
  spec.title = titleInput.value.trim() || spec.title;
  syncSpecView();
});

slugInput.addEventListener("change", () => {
  spec.slug = slugInput.value.trim() || spec.slug;
  syncSpecView();
});

async function renderScene() {
  if (rendering) return;
  rendering = true;
  setRenderBusy(true, "Rendering");
  try {
    const data = await postJson("/api/render", { spec });
    if (!data.ok) throw new Error(data.error || "Render failed");
    showPreview(data.image_url);
    setLink(pngLink, data.image_url);
    setLink(blendLink, data.blend_url);
    setLink(specLink, data.spec_url);
    renderStatus.textContent = "Rendered";
    addMessage("assistant", `Rendered ${data.plan.title}.`);
  } catch (error) {
    renderStatus.textContent = "Error";
    addMessage("assistant", error.message);
  } finally {
    rendering = false;
    setRenderBusy(false);
  }
}

async function dryRunScene() {
  try {
    const data = await postJson("/api/plan", { spec });
    if (!data.ok) throw new Error(data.error || "Dry run failed");
    addMessage("assistant", `Plan OK: ${data.plan.png}`);
    renderStatus.textContent = "Plan OK";
  } catch (error) {
    renderStatus.textContent = "Plan error";
    addMessage("assistant", error.message);
  }
}

function syncSpecView() {
  titleInput.value = spec.title || "";
  slugInput.value = spec.slug || "";
  specEditor.value = JSON.stringify(spec, null, 2);
  const count = Array.isArray(spec.elements) ? spec.elements.length : 0;
  specMeta.textContent = `${count} elements`;
}

function addMessage(role, text) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function showPreview(url) {
  previewImage.onload = () => {
    previewImage.hidden = false;
    emptyPreview.hidden = true;
  };
  previewImage.src = url;
}

function setLink(link, url) {
  link.href = url;
  link.hidden = false;
}

function setRenderBusy(isBusy, label = "Idle") {
  document.getElementById("renderBtn").disabled = isBusy;
  renderStatus.textContent = label;
}
