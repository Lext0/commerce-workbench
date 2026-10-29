"use strict";

const state = { workspace: null, saving: false };
const nameInput = document.querySelector("#workspace-name");
const saveButton = document.querySelector("#save-button");
const saveState = document.querySelector("#save-state");
const formMessage = document.querySelector("#form-message");
const reloadButton = document.querySelector("#reload-workspace");

class RequestError extends Error {
  constructor(status) { super(`Request failed (${status})`); this.status = status; }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new RequestError(response.status);
    return await response.json();
  } finally { clearTimeout(timer); }
}

function connection(ready) {
  const dot = document.querySelector("#connection-dot");
  dot.className = `connection-dot ${ready ? "ready" : "error"}`;
  document.querySelector("#connection-text").textContent = ready ? "工作台连接正常" : "连接暂时不可用";
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function renderWorkspace() {
  document.querySelectorAll("[data-workspace-name]").forEach(element => { element.textContent = state.workspace.name; });
  document.querySelector("#updated-at").textContent = formatDate(state.workspace.updated_at);
  document.title = `${state.workspace.name} · 商品工作台`;
}

function validateName() {
  const name = nameInput.value.trim();
  const count = Array.from(name).length;
  let error = "";
  if (!count || count > 80) error = "请填写 1 到 80 个字符的工作台名称。";
  if (/[\x00-\x1f\x7f]/.test(name)) error = "名称中不能包含换行或控制字符。";
  document.querySelector("#name-count").textContent = `${count} / 80`;
  const errorElement = document.querySelector("#name-error");
  errorElement.textContent = error;
  errorElement.hidden = !error;
  nameInput.setAttribute("aria-invalid", String(Boolean(error)));
  saveButton.disabled = Boolean(error) || !state.workspace || state.saving || name === state.workspace.name;
  if (!state.saving) saveState.textContent = !state.workspace ? "尚未读取" : name === state.workspace.name ? "与已保存内容一致" : "有未保存的修改";
  return !error;
}

function message(text, isError = false) {
  formMessage.textContent = text;
  formMessage.className = `message${isError ? " error" : ""}`;
  formMessage.hidden = !text;
}

async function loadWorkspace() {
  const retryButton = document.querySelector("#retry-load");
  retryButton.disabled = true;
  reloadButton.disabled = true;
  try {
    state.workspace = await request("/api/workspace");
    renderWorkspace();
    nameInput.value = state.workspace.name;
    document.querySelector("#settings-fields").disabled = false;
    document.querySelector("#load-error").hidden = true;
    reloadButton.hidden = true;
    message("");
    connection(true);
    validateName();
  } catch {
    connection(false);
    document.querySelector("#load-error").hidden = false;
  } finally {
    retryButton.disabled = false;
    reloadButton.disabled = false;
  }
}

function route() {
  const hash = window.location.hash;
  const view = !hash || hash === "#/" || hash === "#main" ? "overview" : hash === "#/settings" ? "settings" : "missing";
  document.querySelectorAll("[data-view]").forEach(element => { element.hidden = element.dataset.view !== view; });
  document.querySelectorAll("[data-route]").forEach(element => {
    element.classList.toggle("active", element.dataset.route === view);
    if (element.dataset.route === view) element.setAttribute("aria-current", "page");
    else element.removeAttribute("aria-current");
  });
  document.querySelector("#current-section").textContent = { overview: "概览", settings: "设置", missing: "页面未找到" }[view];
}

nameInput.addEventListener("input", () => { message(""); validateName(); });
document.querySelector("#retry-load").addEventListener("click", loadWorkspace);
reloadButton.addEventListener("click", loadWorkspace);
document.querySelector("#settings-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!state.workspace || state.saving || !validateName()) return;
  state.saving = true;
  const submittedName = nameInput.value.trim();
  document.querySelector("#settings-fields").disabled = true;
  saveButton.disabled = true;
  saveButton.textContent = "正在保存";
  saveState.textContent = "";
  message("");
  try {
    state.workspace = await request("/api/workspace", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: submittedName, revision: state.workspace.revision }),
    });
    nameInput.value = state.workspace.name;
    renderWorkspace();
    connection(true);
    reloadButton.hidden = true;
    message("设置已保存。");
  } catch (error) {
    if (error.status === 409) {
      message("名称已在其他页面修改。请重新载入最新设置后再修改。", true);
      reloadButton.hidden = false;
    } else if (error.status === 422) {
      message("名称格式不正确，请检查长度和内容后再保存。", true);
    } else {
      connection(false);
      message("暂时无法保存，输入的内容已保留，请稍后重试。", true);
    }
  } finally {
    state.saving = false;
    document.querySelector("#settings-fields").disabled = false;
    saveButton.textContent = "保存设置";
    validateName();
  }
});

document.querySelector("#today").textContent = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(new Date());
window.addEventListener("hashchange", route);
route();
loadWorkspace();
