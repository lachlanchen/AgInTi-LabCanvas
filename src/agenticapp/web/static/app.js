let spec = null;
let settings = null;
let artifacts = [];
let targets = [];
let selectedArtifactId = "";
let rendering = false;

const messages = document.getElementById("messages");
const chatStatus = document.getElementById("chatStatus");
const renderStatus = document.getElementById("renderStatus");
const previewImage = document.getElementById("previewImage");
const emptyPreview = document.getElementById("emptyPreview");
const artifactViewer = document.getElementById("artifactViewer");
const artifactList = document.getElementById("artifactList");
const artifactTitle = document.getElementById("artifactTitle");
const artifactMeta = document.getElementById("artifactMeta");
const artifactKind = document.getElementById("artifactKind");
const specEditor = document.getElementById("specEditor");
const specMeta = document.getElementById("specMeta");
const titleInput = document.getElementById("titleInput");
const slugInput = document.getElementById("slugInput");
const pngLink = document.getElementById("pngLink");
const blendLink = document.getElementById("blendLink");
const specLink = document.getElementById("specLink");
const backendStatus = document.getElementById("backendStatus");
const themeButton = document.getElementById("themeBtn");
const targetSelect = document.getElementById("targetSelect");
const targetInstruction = document.getElementById("targetInstruction");

init();

async function init() {
  const [specResponse] = await Promise.all([fetch("/api/spec"), loadSettings(), loadTargets(), loadArtifacts()]);
  const data = await specResponse.json();
  spec = data.spec;
  syncSpecView();
  if (data.preview_url && !artifacts.length) {
    showPreview(data.preview_url);
  }
  addMessage("assistant", "Scene loaded. Ask for components, paper figure grids, OpenSCAD exports, or BioRender setup.");
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
    if (data.artifacts) {
      setArtifacts(data.artifacts);
    }
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
document.getElementById("figureBtn").addEventListener("click", generateFigureGrid);
document.getElementById("openscadBtn").addEventListener("click", exportOpenScad);
document.getElementById("templateBtn").addEventListener("click", init);
document.getElementById("dispatchTargetBtn").addEventListener("click", dispatchRegistryTarget);
themeButton.addEventListener("click", toggleTheme);
document.getElementById("openBioRenderBtn").addEventListener("click", () => {
  const url = document.getElementById("biorenderUrl").value.trim() || "https://app.biorender.com/";
  window.open(url.includes("/mcp") ? "https://app.biorender.com/" : url, "_blank", "noopener");
});

document.getElementById("applySpecBtn").addEventListener("click", () => {
  try {
    spec = JSON.parse(specEditor.value);
    syncSpecView();
    addMessage("assistant", "Scene JSON applied.");
  } catch (error) {
    addMessage("assistant", `JSON error: ${error.message}`);
  }
});

document.getElementById("settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const nextSettings = collectSettings();
  try {
    const data = await postJson("/api/settings", { settings: nextSettings });
    settings = data.settings;
    syncSettingsView(data.status);
    addMessage("assistant", "Backend settings saved.");
  } catch (error) {
    addMessage("assistant", error.message);
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
    setLink(pngLink, data.image_url);
    setLink(blendLink, data.blend_url);
    setLink(specLink, data.spec_url);
    setArtifacts(data.artifacts);
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

async function generateFigureGrid() {
  renderStatus.textContent = "Generating grid";
  const payload = {
    prompt: document.getElementById("figurePrompt").value.trim(),
    rows: Number(document.getElementById("figureRows").value || 2),
    cols: Number(document.getElementById("figureCols").value || 3),
  };
  try {
    const data = await postJson("/api/figure-grid", payload);
    if (!data.ok) throw new Error(data.error || "Figure grid failed");
    setArtifacts(data.artifacts);
    setLink(pngLink, data.figure_url);
    const agintiSummary = data.aginti?.summary ? ` AgInTi: ${data.aginti.summary}` : "";
    addMessage("assistant", `Generated a ${data.rows}x${data.cols} paper figure grid.${agintiSummary}`);
    renderStatus.textContent = "Grid ready";
  } catch (error) {
    renderStatus.textContent = "Grid error";
    addMessage("assistant", error.message);
  }
}

async function exportOpenScad() {
  renderStatus.textContent = "Exporting CAD";
  try {
    const data = await postJson("/api/openscad-export", { spec });
    if (!data.ok) throw new Error(data.error || "OpenSCAD export failed");
    setArtifacts(data.artifacts);
    addMessage("assistant", `Exported OpenSCAD: ${data.export.path}`);
    renderStatus.textContent = "CAD ready";
  } catch (error) {
    renderStatus.textContent = "CAD error";
    addMessage("assistant", error.message);
  }
}

async function loadSettings() {
  const response = await fetch("/api/settings");
  const data = await response.json();
  settings = data.settings;
  syncSettingsView(data.status);
}

async function loadArtifacts() {
  const response = await fetch("/api/artifacts");
  const data = await response.json();
  setArtifacts(data);
}

async function loadTargets() {
  const response = await fetch("/api/targets");
  const data = await response.json();
  targets = Array.isArray(data.targets) ? data.targets : [];
  renderTargetOptions();
}

async function dispatchRegistryTarget() {
  const target = targetSelect.value;
  const instruction = targetInstruction.value.trim();
  if (!target || !instruction) {
    addMessage("assistant", "Choose a target and enter an instruction first.");
    return;
  }
  renderStatus.textContent = "Dispatching";
  try {
    const data = await postJson("/api/dispatch", {
      target,
      instruction,
      dry_run: document.getElementById("dispatchDryRun").checked,
    });
    setArtifacts(data.artifacts);
    const status = data.dispatch?.status || "done";
    addMessage("assistant", `Target dispatch ${status}: ${target}.`);
    renderStatus.textContent = "Dispatch ready";
  } catch (error) {
    renderStatus.textContent = "Dispatch error";
    addMessage("assistant", error.message);
  }
}

function renderTargetOptions() {
  targetSelect.innerHTML = "";
  targets.forEach((target) => {
    const option = document.createElement("option");
    option.value = target.name;
    option.textContent = `${target.name} (${target.transport})`;
    option.disabled = !target.enabled;
    targetSelect.appendChild(option);
  });
  if (targets.length && !targetInstruction.value) {
    targetInstruction.value = "Prepare a paper figure workflow for this target";
  }
}

function setArtifacts(bundle) {
  artifacts = Array.isArray(bundle?.items) ? bundle.items : [];
  selectedArtifactId = bundle?.selected_id || artifacts.find((item) => item.selected)?.id || selectedArtifactId;
  renderArtifactList();
  const selected = artifacts.find((item) => item.id === selectedArtifactId) || artifacts[0];
  if (selected) selectArtifact(selected.id);
}

function renderArtifactList() {
  artifactList.innerHTML = "";
  if (!artifacts.length) {
    const empty = document.createElement("p");
    empty.className = "status artifact-empty";
    empty.textContent = "No artifacts yet.";
    artifactList.appendChild(empty);
    return;
  }
  artifacts.forEach((item) => {
    const button = document.createElement("button");
    button.className = "artifact-item";
    button.type = "button";
    button.dataset.selected = item.id === selectedArtifactId ? "true" : "false";
    button.addEventListener("click", () => selectArtifact(item.id));

    const top = document.createElement("span");
    top.className = "artifact-item-top";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const kind = document.createElement("span");
    kind.textContent = item.kind;
    top.append(title, kind);

    const meta = document.createElement("small");
    meta.textContent = item.source || item.path;
    const preview = document.createElement("em");
    preview.textContent = item.preview || item.path;
    button.append(top, meta, preview);
    artifactList.appendChild(button);
  });
}

async function selectArtifact(id) {
  selectedArtifactId = id;
  renderArtifactList();
  const item = artifacts.find((candidate) => candidate.id === id);
  if (!item) return;
  artifactTitle.textContent = item.title;
  artifactMeta.textContent = item.path;
  artifactKind.textContent = item.kind;
  if (item.kind === "image") {
    resetViewer();
    showPreview(item.url);
    setLink(pngLink, item.url);
    return;
  }
  resetViewer();
  previewImage.hidden = true;
  emptyPreview.hidden = true;
  const body = document.createElement("pre");
  body.className = "text-artifact";
  if (["json", "text", "openscad"].includes(item.kind)) {
    const response = await fetch(item.url);
    body.textContent = await response.text();
  } else {
    body.textContent = `Artifact path: ${item.path}`;
  }
  artifactViewer.appendChild(body);
}

function syncSpecView() {
  titleInput.value = spec.title || "";
  slugInput.value = spec.slug || "";
  specEditor.value = JSON.stringify(spec, null, 2);
  const count = Array.isArray(spec.elements) ? spec.elements.length : 0;
  specMeta.textContent = `${count} elements`;
}

function syncSettingsView(status = {}) {
  if (!settings) return;
  document.getElementById("agintiCommand").value = settings.aginti?.command || "aginti";
  document.getElementById("agintiWorkspace").value = settings.aginti?.workspace || "../Agent/AgInTiFlow";
  document.getElementById("agintiProvider").value = settings.aginti?.image_provider || "grsai";
  document.getElementById("agintiModel").value = settings.aginti?.image_model || "nano-banana-2";
  document.getElementById("agintiDryRun").checked = Boolean(settings.aginti?.dry_run);
  document.getElementById("biorenderUrl").value = settings.biorender?.mcp_url || "https://mcp.services.biorender.com/mcp";
  document.getElementById("biorenderEnv").value = settings.biorender?.auth_env || "BIORENDER_API_KEY";
  document.getElementById("toolBlender").checked = settings.toolchain?.blender !== false;
  document.getElementById("toolOpenScad").checked = settings.toolchain?.openscad !== false;
  document.getElementById("toolAgintiImage").checked = settings.toolchain?.aginti_image !== false;
  document.getElementById("toolBioRender").checked = Boolean(settings.toolchain?.biorender);
  document.getElementById("toolTargetRegistry").checked = settings.toolchain?.target_registry !== false;
  const agintiReady = status.aginti?.command_path ? "AgInTi ready" : "AgInTi missing";
  const bioReady = status.biorender?.auth_env_present ? "BioRender key present" : "BioRender key via env";
  backendStatus.textContent = `${agintiReady} · ${bioReady}`;
  syncThemeButton();
}

function collectSettings() {
  return {
    ...settings,
    aginti: {
      ...settings.aginti,
      command: document.getElementById("agintiCommand").value.trim() || "aginti",
      workspace: document.getElementById("agintiWorkspace").value.trim() || "../Agent/AgInTiFlow",
      image_provider: document.getElementById("agintiProvider").value.trim() || "grsai",
      image_model: document.getElementById("agintiModel").value.trim() || "nano-banana-2",
      dry_run: document.getElementById("agintiDryRun").checked,
    },
    biorender: {
      ...settings.biorender,
      mcp_url: document.getElementById("biorenderUrl").value.trim() || "https://mcp.services.biorender.com/mcp",
      auth_env: document.getElementById("biorenderEnv").value.trim() || "BIORENDER_API_KEY",
    },
    toolchain: {
      ...settings.toolchain,
      blender: document.getElementById("toolBlender").checked,
      openscad: document.getElementById("toolOpenScad").checked,
      aginti_image: document.getElementById("toolAgintiImage").checked,
      biorender: document.getElementById("toolBioRender").checked,
      target_registry: document.getElementById("toolTargetRegistry").checked,
    },
  };
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("appautoaction-theme", next);
  syncThemeButton();
}

function syncThemeButton() {
  const isDark = document.documentElement.dataset.theme === "dark";
  themeButton.textContent = isDark ? "Light" : "Dark";
  themeButton.setAttribute("aria-label", isDark ? "Switch to bright theme" : "Switch to dark theme");
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

function resetViewer() {
  [...artifactViewer.querySelectorAll(".text-artifact")].forEach((node) => node.remove());
  emptyPreview.hidden = false;
}

function setLink(link, url) {
  link.href = url;
  link.hidden = false;
}

function setRenderBusy(isBusy, label = "Idle") {
  document.getElementById("renderBtn").disabled = isBusy;
  renderStatus.textContent = label;
}
