import { app } from "../../../scripts/app.js";

const QUERY_KEY = "workflow";
const WORKFLOW_PREFIX = "workflows/";
const BRIDGE_MESSAGE_TYPE = "dapao:open-workflow";
const WORKFLOW_INDEX_TAB_ID = "dapao-workflow-index";
const INDEX_PAGE_URL = new URL("./index.html", import.meta.url);
let workflowIndexFrame = null;

function normalizeUserDataPath(rawPath) {
  let path = String(rawPath || "").trim().replace(/\\/g, "/");
  if (!path) throw new Error("工作流路径为空");
  if (path.includes("\0") || /^[a-zA-Z]:\//.test(path) || path.startsWith("/")) {
    throw new Error("只允许载入 ComfyUI 用户目录内的相对工作流路径");
  }

  if (!path.startsWith(WORKFLOW_PREFIX)) path = WORKFLOW_PREFIX + path;
  const segments = path.split("/");
  if (segments.some((segment) => segment === "." || segment === "..")) {
    throw new Error("工作流路径不能包含 . 或 ..");
  }
  return path;
}

function notify(severity, summary, detail) {
  const toast = app.extensionManager?.toast;
  if (toast?.add) {
    toast.add({ severity, summary, detail, life: severity === "error" ? 8000 : 3500 });
  } else if (severity === "error") {
    console.error(`[Workflow Index] ${summary}: ${detail}`);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForStartup(timeoutMs = 120000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (app.canvas && typeof app.loadGraphData === "function") {
      const splash = document.getElementById("splash-loader");
      const splashHidden = !splash
        || splash.hidden
        || getComputedStyle(splash).display === "none"
        || getComputedStyle(splash).visibility === "hidden";
      if (splashHidden) return;
    }
    await sleep(100);
  }
}

async function loadWorkflowByPath(rawPath, openSource) {
  let userDataPath;
  try {
    userDataPath = normalizeUserDataPath(rawPath);
  } catch (error) {
    notify("error", "工作流链接无效", error.message);
    return;
  }

  await waitForStartup();
  await sleep(250);

  try {
    const response = await app.api.getUserData(userDataPath, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`读取工作流失败 (${response.status} ${response.statusText})`);
    }

    const workflow = await response.json();
    if (!workflow || typeof workflow !== "object" || Array.isArray(workflow)) {
      throw new Error("文件不是有效的 ComfyUI 工作流");
    }
    if (!Array.isArray(workflow.nodes)) {
      throw new Error("这是 API 格式文件，画布不能直接打开");
    }

    const filename = userDataPath.split("/").pop() || "工作流";
    const workflowStore = app.extensionManager?.workflow;
    const temporaryWorkflow = workflowStore?.createTemporary
      ? workflowStore.createTemporary(filename, workflow)
      : null;
    await app.loadGraphData(
      workflow,
      true,
      true,
      temporaryWorkflow,
      { openSource },
    );
    notify("success", "工作流已打开", filename);
  } catch (error) {
    console.error("[Workflow Index] Failed to open workflow:", error);
    notify("error", "无法打开工作流", error instanceof Error ? error.message : String(error));
  }
}

async function openWorkflowFromUrl() {
  const url = new URL(window.location.href);
  const requested = url.searchParams.get(QUERY_KEY);
  if (requested == null) return;

  // Remove the startup intent before loading so refreshing the tab will not load it twice.
  url.searchParams.delete(QUERY_KEY);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  await loadWorkflowByPath(requested, "workflow_index_url");
}

function registerWorkflowIndexSidebar() {
  const manager = app.extensionManager;
  if (!manager?.registerSidebarTab) return false;
  try {
    const tabs = manager.getSidebarTabs?.() || [];
    if (tabs.some(tab => tab.id === WORKFLOW_INDEX_TAB_ID)) {
      app.__dapaoWorkflowIndexSidebarRegistered = true;
      return true;
    }
  } catch {}
  if (manager.sidebarTab?.$subscribe && !app.__dapaoWorkflowIndexSidebarSubscribed) {
    app.__dapaoWorkflowIndexSidebarSubscribed = true;
    manager.sidebarTab.$subscribe((_mutation, state) => {
      if (!workflowIndexFrame) return;
      const activeId = String(state.activeSidebarTabId?.value ?? state.activeSidebarTabId ?? "");
      workflowIndexFrame.style.display =
        activeId === WORKFLOW_INDEX_TAB_ID ? "block" : "none";
    });
  }
  try {
    manager.registerSidebarTab({
      id: WORKFLOW_INDEX_TAB_ID,
      icon: "pi pi-folder-open",
      title: "工作流索引",
      tooltip: "ComfyUI 工作流总索引",
      type: "custom",
      render(element) {
        element.replaceChildren();
        element.style.height = "100%";
        element.style.minHeight = "0";
        element.style.overflow = "hidden";
        const frame = document.createElement("iframe");
        const frameUrl = new URL(INDEX_PAGE_URL);
        frameUrl.searchParams.set("embedded", "1");
        frameUrl.searchParams.set("v", String(Date.now()));
        frame.src = frameUrl.href;
        frame.title = "ComfyUI 工作流总索引";
        frame.allow = "clipboard-read; clipboard-write";
        Object.assign(frame.style, {
          width: "100%",
          height: "100%",
          border: "0",
          display: "block",
          visibility: "visible",
          background: "#f3f5f1",
        });
        element.appendChild(frame);
        workflowIndexFrame = frame;
      },
    });
    app.__dapaoWorkflowIndexSidebarRegistered = true;
    return true;
  } catch (error) {
    app.__dapaoWorkflowIndexSidebarRegistered = false;
    console.error("[Workflow Index] Sidebar registration failed:", error);
    return false;
  }
}

function registerWorkflowIndexSidebarWhenReady(attempt = 0) {
  if (attempt >= 1800) return;
  if (registerWorkflowIndexSidebar()) return;
  window.setTimeout(() => registerWorkflowIndexSidebarWhenReady(attempt + 1), 100);
}

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  if (!event.data || event.data.type !== BRIDGE_MESSAGE_TYPE) return;
  if (workflowIndexFrame && event.source !== workflowIndexFrame.contentWindow) return;
  void loadWorkflowByPath(event.data.path, "workflow_index_sidebar");
});

if (!app.__dapaoWorkflowIndexOpenerRegistered) {
  app.__dapaoWorkflowIndexOpenerRegistered = true;
  app.registerExtension({
    name: "Dapao.WorkflowIndexOpener",
    init() {
      // Sidebar registration is available once the frontend extension manager is initialized.
      registerWorkflowIndexSidebarWhenReady();
      void openWorkflowFromUrl();
    },
  });
  registerWorkflowIndexSidebarWhenReady();
}
