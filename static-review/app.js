const showcaseMode = true;
document.documentElement.classList.toggle("showcase-layout", showcaseMode);

const showcaseTextMap = new Map([
  ["算力资源信息", "算力资源信息"],
  ["ZTW 算力资源信息", "ZTW 算力资源信息"],
  ["资源信息", "资源信息"],
  ["服务记录", "服务记录"],
  ["方案适配", "方案适配"],
  ["需求咨询", "需求咨询"],
  ["合作方申请", "合作方申请"],
  ["企业算力资源信息服务", "企业算力资源信息服务"],
  ["按产品、地区和使用需求，", "按产品、地区和使用需求，"],
  ["了解适合业务场景的算力方案。", "了解适合业务场景的算力方案。"],
  ["统一了解 GPU 计算资源、模型运行支持与设备资源服务，具体条件以正式沟通结果为准。", "统一了解 GPU 计算资源、模型运行支持与设备资源服务，具体条件以正式沟通结果为准。"],
  ["提交需求", "提交需求"],
  ["合作方申请", "合作方申请"],
  ["资源信息概览", "资源信息概览"],
  ["GPU 资源目录", "GPU 资源目录"],
  ["多种", "多种"],
  ["信息参考", "信息参考"],
  ["KAI 数据参考", "KAI 数据参考"],
  ["服务周期", "服务周期"],
  ["按使用需求", "按使用需求"],
  ["资源信息", "资源信息"],
  ["全部信息", "全部信息"],
  ["GPU 计算资源", "GPU 计算资源"],
  ["模型运行支持", "模型运行支持"],
  ["设备资源服务", "设备资源服务"],
  ["规格与服务条件以正式沟通结果为准", "规格与服务条件以正式沟通结果为准"],
  ["信息目录", "信息目录"],
  ["本地服务记录", "本地服务记录"],
  ["查看本页模拟提交的需求记录，不读取真实账户信息。", "查看本页模拟提交的需求记录，不读取真实账户信息。"],
  ["查看资源", "查看资源"],
  ["需求记录", "需求记录"],
  ["记录编号", "记录编号"],
  ["暂无本地需求记录", "暂无本地需求记录"],
  ["从资源信息选择任一方案，即可模拟提交需求。", "从资源信息选择任一方案，即可模拟提交需求。"],
  ["查看资源信息", "查看资源信息"],
  ["方案适配", "方案适配"],
  ["根据本地需求记录调整更适合当前任务的资源方案。", "根据本地需求记录调整更适合当前任务的资源方案。"],
  ["需求数量（GPU时）", "需求数量（GPU时）"],
  ["提交后仅生成本地适配反馈，不会修改实际服务记录。", "提交后仅生成本地适配反馈，不会修改实际服务记录。"],
  ["提交适配需求", "提交适配需求"],
  ["需求登记", "需求登记"],
  ["选择资源、地区和使用时长，生成一条可查询的本地需求记录。", "选择资源、地区和使用时长，生成一条可查询的本地需求记录。"],
  ["需求数量", "需求数量"],
  ["使用方式", "使用方式"],
  ["长期使用", "长期使用"],
  ["服务方式", "服务方式"],
  ["标准服务", "标准服务"],
  ["人工确认", "人工确认"],
  ["按所选时长使用", "按所选时长使用"],
  ["确认后沟通服务信息", "确认后沟通服务信息"],
  ["本页用于展示需求填写流程。提交后仅生成本地记录，可在服务记录中查看或取消。", "本页用于展示需求填写流程。提交后仅生成本地记录，可在服务记录中查看或取消。"],
  ["提交需求", "提交需求"],
  ["需求咨询", "需求咨询"],
  ["合作申请", "合作申请"],
  ["填写可提供的资源服务信息，模拟提交合作申请。", "填写可提供的资源服务信息，模拟提交合作申请。"],
  ["可服务时长（GPU时）", "可服务时长（GPU时）"],
  ["资源环境", "资源环境"],
  ["已登记资源", "已登记资源"],
  ["合作数据中心", "合作数据中心"],
  ["企业自有环境", "企业自有环境"],
  ["网络条件", "网络条件"],
  ["高速互联", "高速互联"],
  ["网络条件待确认", "网络条件待确认"],
  ["同意合作信息在正式展示前接受审核与确认", "同意合作信息在正式展示前接受审核与确认"],
  ["提交后仅显示本地成功反馈，不会向外部系统发送数据。", "提交后仅显示本地成功反馈，不会向外部系统发送数据。"],
  ["提交合作申请", "提交合作申请"],
  ["了解 ZTW 的服务定位、资源范围与需求服务流程。", "了解 ZTW 的服务定位、资源范围与需求服务流程。"],
  ["ZTW 面向资源需求企业与资源合作方，提供 GPU 资源信息、需求登记、服务记录和合作申请等统一服务入口。", "ZTW 面向资源需求企业与资源合作方，提供 GPU 资源信息、需求登记、服务记录和合作申请等统一服务入口。"],
  ["平台围绕算力产品、使用地区、使用时长和服务方式组织信息，帮助企业清楚表达需求，也让合作方能够按统一字段登记资源信息。", "平台围绕算力产品、使用地区、使用时长和服务方式组织信息，帮助企业清楚表达需求，也让合作方能够按统一字段登记资源信息。"],
  ["资源需求企业与资源合作方", "资源需求企业与资源合作方"],
  ["GPU 计算、模型运行与设备资源服务", "GPU 计算、模型运行与设备资源服务"],
  ["数据参考", "数据参考"],
  ["需求方式", "需求方式"],
  ["提交需求，沟通确认", "提交需求，沟通确认"],
  ["从了解资源到管理需求记录，为需求企业和资源合作方提供清晰入口。", "从了解资源到管理需求记录，为需求企业和资源合作方提供清晰入口。"],
  ["了解与比较", "了解与比较"],
  ["按资源类型查看 GPU 计算资源、模型运行支持和设备资源服务，了解统一规格与信息参考。", "按资源类型查看 GPU 计算资源、模型运行支持和设备资源服务，了解统一规格与信息参考。"],
  ["选择地区、数量、使用时长和服务方式，形成结构化需求，减少信息遗漏。", "选择地区、数量、使用时长和服务方式，形成结构化需求，减少信息遗漏。"],
  ["记录与适配", "记录与适配"],
  ["集中查看需求记录，支持取消、再次提交和方案适配，保持每次操作路径清楚可查。", "集中查看需求记录，支持取消、再次提交和方案适配，保持每次操作路径清楚可查。"],
  ["合作方可填写资源类型、可服务时长、资源环境和网络条件，为后续审核确认准备资料。", "合作方可填写资源类型、可服务时长、资源环境和网络条件，为后续审核确认准备资料。"],
  ["当前静态页面保留前端操作，正式服务条件以沟通确认结果为准。", "当前静态页面保留前端操作，正式服务条件以沟通确认结果为准。"],
  ["了解资源", "了解资源"],
  ["按产品类型了解资源和服务说明。", "按产品类型了解资源和服务说明。"],
  ["补充地区、数量、时长和服务方式。", "补充地区、数量、时长和服务方式。"],
  ["查看需求状态，支持取消和再次提交。", "查看需求状态，支持取消和再次提交。"],
  ["具体规格、服务条件和实施安排以正式沟通结果为准。", "具体规格、服务条件和实施安排以正式沟通结果为准。"],
  ["这些说明帮助访客了解资源信息与需求服务流程。", "这些说明帮助访客了解资源信息与需求服务流程。"],
  ["可根据 GPU 型号、显存、使用地区、需求数量和时长查看信息。无法确定时，可先提交需求咨询。", "可根据 GPU 型号、显存、使用地区、需求数量和时长查看信息。无法确定时，可先提交需求咨询。"],
  ["需求记录保存在哪里？", "需求记录保存在哪里？"],
  ["需求记录保存在当前浏览器的本地存储中，不会发送到服务器。清除浏览器数据后，记录可能被删除。", "需求记录保存在当前浏览器的本地存储中，不会发送到服务器。清除浏览器数据后，记录可能被删除。"],
  ["服务条件如何确认？", "服务条件如何确认？"],
  ["页面提供 KAI 数据参考，不展示固定服务价格。具体规格、服务条件和实施安排以正式沟通结果为准。", "页面提供 KAI 数据参考，不展示固定服务价格。具体规格、服务条件和实施安排以正式沟通结果为准。"],
  ["合作方提交后会立即展示吗？", "合作方提交后会立即展示吗？"],
  ["不会。当前提交仅演示前端流程，正式展示还需完成资料核对与业务审核。", "不会。当前提交仅演示前端流程，正式展示还需完成资料核对与业务审核。"],
  ["从资源信息开始", "从资源信息开始"],
  ["浏览资源信息，或者进入合作方申请登记服务信息。", "浏览资源信息，或者进入合作方申请登记服务信息。"],
  ["查看资源信息", "查看资源信息"],
  ["提交合作申请", "提交合作申请"],
  ["本地需求记录", "本地需求记录"],
  ["需求记录已生成", "需求记录已生成"],
  ["记录已保存在当前浏览器，可前往服务记录查看、取消或再次提交。", "记录已保存在当前浏览器，可前往服务记录查看、取消或再次提交。"],
  ["查看记录", "查看记录"],
  ["继续查看", "继续查看"],
  ["再次提交", "再次提交"],
  ["取消记录", "取消记录"],
  ["本地需求记录已取消。", "本地需求记录已取消。"],
  ["本地需求记录已清空。", "本地需求记录已清空。"],
  ["已带入上一条本地需求，可调整后再次提交。", "已带入上一条本地需求，可调整后再次提交。"],
  ["请先创建本地需求记录", "请先创建本地需求记录"],
  ["请先完成标记的需求信息。", "请先完成标记的需求信息。"],
  ["请先完成标记的适配信息。", "请先完成标记的适配信息。"],
  ["本地适配需求已生成，未发送到服务器。", "本地适配需求已生成，未发送到服务器。"],
  ["本地合作申请已生成，未发送到服务器。", "本地合作申请已生成，未发送到服务器。"],
  ["需求内容", "需求内容"],
]);

const showcaseResourceCopy = {
  "h100-80gb": {
    tag: "GPU 计算资源",
    specs: [["显存", "80GB HBM3"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  "a100-80gb": {
    tag: "GPU 计算资源",
    specs: [["显存", "80GB HBM2e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  "h200-141gb": {
    tag: "GPU 计算资源",
    specs: [["显存", "141GB HBM3e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  "b300-262gb": {
    tag: "GPU 计算资源",
    specs: [["显存", "262GB HBM3e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  "model-inference": {
    tag: "模型运行支持",
    name: "按需模型运行支持",
    specs: [["资源", "ZTW GPU 资源"], ["方式", "方案沟通确认"], ["管理", "统一服务记录"]],
    status: "服务条件可咨询",
  },
  "gpu-hosting": {
    tag: "设备资源服务",
    name: "GPU 设备资源服务",
    specs: [["资源", "设备信息登记"], ["服务", "条件沟通确认"], ["协同", "合作方申请"]],
    status: "服务方案可咨询",
  },
};

const resources = [
  {
    id: "h100-80gb",
    type: "gpu",
    tag: "GPU 计算资源",
    className: "gpu",
    name: "NVIDIA H100 80GB",
    specs: [["显存", "80GB HBM3"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  {
    id: "a100-80gb",
    type: "gpu",
    tag: "GPU 计算资源",
    className: "gpu",
    name: "NVIDIA A100 80GB",
    specs: [["显存", "80GB HBM2e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  {
    id: "h200-141gb",
    type: "gpu",
    tag: "GPU 计算资源",
    className: "gpu",
    name: "NVIDIA H200 141GB",
    specs: [["显存", "141GB HBM3e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  {
    id: "b300-262gb",
    type: "gpu",
    tag: "GPU 计算资源",
    className: "gpu",
    name: "NVIDIA B300 262GB",
    specs: [["显存", "262GB HBM3e"], ["服务", "按需求确认"], ["信息", "KAI 数据参考"]],
    status: "支持提交服务需求",
  },
  {
    id: "model-inference",
    type: "ai",
    tag: "模型运行支持",
    className: "ai",
    name: "按需模型运行支持",
    specs: [["资源", "ZTW GPU 资源"], ["方式", "方案沟通确认"], ["管理", "统一服务记录"]],
    status: "服务方案可咨询",
  },
  {
    id: "gpu-hosting",
    type: "rack",
    tag: "设备资源服务",
    className: "rack",
    name: "GPU 设备资源服务",
    specs: [["资源", "设备信息登记"], ["服务", "条件沟通确认"], ["协同", "合作方申请"]],
    status: "服务方案可咨询",
  },
];

const storageKey = "wod.info.requests.v1";
const allowedStatuses = new Set(["待确认", "已取消"]);
const resourceGrid = document.querySelector("#resourceGrid");
const resourceCount = document.querySelector("#resourceCount");
const views = Array.from(document.querySelectorAll(".view"));
const topNavButtons = Array.from(document.querySelectorAll(".nav [data-nav]"));
const quoteForm = document.querySelector("#quoteForm");
const scheduleForm = document.querySelector("#scheduleForm");
const supplierForm = document.querySelector("#supplierForm");
const quoteResource = document.querySelector("#quoteResource");
const scheduleCurrent = document.querySelector("#scheduleCurrent");
const scheduleTarget = document.querySelector("#scheduleTarget");
const supplierType = document.querySelector("#supplierType");
const orderTableBody = document.querySelector("#orderTableBody");
const orderEmpty = document.querySelector("#orderEmpty");
const tableScroll = document.querySelector(".table-scroll");
const orderCount = document.querySelector("#orderCount");
const clearOrdersButton = document.querySelector("#clearOrders");
const orderModal = document.querySelector("#orderModal");
const orderSummary = document.querySelector("#orderSummary");
const viewOrderButton = document.querySelector("#viewOrderButton");
const toastElement = document.querySelector("#toast");
const toastTitle = document.querySelector("#toastTitle");
const toastMessage = document.querySelector("#toastMsg");
const modalCard = orderModal.querySelector(".modal-card");
const inertTargets = [document.querySelector(".topbar"), document.querySelector(".side-rail"), document.querySelector("#main-content"), document.querySelector("body > footer")].filter(Boolean);
let toastTimer;
let viewFocusTimer;
let lastModalFocus;
let orders = loadOrders();

function displayText(text) {
  return showcaseMode ? (showcaseTextMap.get(text) ?? text) : text;
}

function displayResource(resource) {
  if (!showcaseMode) return resource;
  return { ...resource, ...showcaseResourceCopy[resource.id] };
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function applyShowcaseCopy() {
  if (!showcaseMode) return;

  document.title = "ZTW 算力资源信息";
  const description = document.querySelector('meta[name="description"]');
  if (description) description.content = "ZTW 算力资源信息静态页，提供资源信息展示、需求咨询、服务记录和合作申请演示。";

  document.querySelector(".brand")?.setAttribute("aria-label", "打开资源信息");
  document.querySelector(".hero-brief")?.setAttribute("aria-label", "资源信息概览");
  document.querySelector(".filters")?.setAttribute("aria-label", "筛选资源信息");

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  textNodes.forEach((node) => {
    const source = node.nodeValue;
    const trimmed = source.trim();
    const replacement = showcaseTextMap.get(trimmed);
    if (replacement) node.nodeValue = source.replace(trimmed, replacement);
  });

  const contact = document.querySelector('.footer-links [data-toast]');
  if (contact) contact.dataset.toast = "联系方式将在正式资料确认后补充。";
}

applyShowcaseCopy();

function renderResources(filter = "all") {
  resourceGrid.replaceChildren();
  const filtered = resources.filter((resource) => filter === "all" || resource.type === filter);
  resourceCount.textContent = `当前展示 ${filtered.length} 项`;

  filtered.forEach((resource) => {
    const display = displayResource(resource);
    const card = createElement("article", "card");
    card.dataset.resourceId = resource.id;
    card.dataset.resourceType = resource.type;

    const cardHeader = createElement("div", "card-header");
    cardHeader.append(
      createElement("span", `card-tag ${resource.className}`, display.tag),
      createElement("span", "card-availability", "可咨询"),
    );
    card.append(cardHeader);
    card.append(createElement("h3", "", display.name));

    const specList = createElement("div", "card-specs");
    display.specs.forEach(([label, value]) => {
      const spec = createElement("div", "spec");
      const title = createElement("b", "", `${label}：`);
      spec.append(title, document.createTextNode(value));
      specList.append(spec);
    });
    card.append(specList);
    card.append(createElement("p", "resource-note", display.status));

    const cardFooter = createElement("div", "card-footer");
    const price = createElement("div", "price");
    price.append(createElement("strong", "", displayText("需求咨询")), createElement("span", "", "按需求确认"));

    const action = createElement("button", "btn btn-outline", displayText("需求咨询"));
    action.type = "button";
    action.dataset.buyResource = resource.id;
    cardFooter.append(price, action);
    card.append(cardFooter);
    resourceGrid.append(card);
  });
}

function populateResourceSelects() {
  [quoteResource, scheduleTarget, supplierType].forEach((select) => select.replaceChildren());

  resources.forEach((resource) => {
    const name = displayResource(resource).name;
    const quoteOption = new Option(name, resource.id);
    const targetOption = new Option(name, resource.id);
    const supplierOption = new Option(name, resource.id);
    quoteResource.add(quoteOption);
    scheduleTarget.add(targetOption);
    supplierType.add(supplierOption);
  });
}

function showView(id, options = {}) {
  const target = document.querySelector(`#view-${id}`) ?? document.querySelector("#view-resources");
  if (!target) return;

  views.forEach((view) => {
    const active = view === target;
    view.classList.toggle("active", active);
    view.hidden = !active;
  });

  topNavButtons.forEach((button) => {
    const active = button.dataset.nav === target.id.replace("view-", "");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });

  if (id === "manage") renderOrders();
  if (id === "schedule") updateScheduleOptions();
  if (options.scroll !== false) window.scrollTo({ top: 0, behavior: "smooth" });

  window.clearTimeout(viewFocusTimer);
  if (options.focusHeading !== false) {
    const headingId = target.getAttribute("aria-labelledby");
    const heading = headingId ? document.getElementById(headingId) : null;
    if (heading) {
      heading.tabIndex = -1;
      viewFocusTimer = window.setTimeout(() => {
        if (!target.hidden) heading.focus({ preventScroll: true });
      }, options.scroll === false ? 0 : 220);
    }
  }
}

function openQuote(resourceId) {
  if (resources.some((resource) => resource.id === resourceId)) quoteResource.value = resourceId;
  showView("quote", { focusHeading: false });
  window.setTimeout(() => quoteResource.focus({ preventScroll: true }), 220);
}

document.addEventListener("click", (event) => {
  const navButton = event.target.closest("[data-nav]");
  if (navButton) {
    if (navButton.closest("#orderModal")) closeOrderModal(false);
    showView(navButton.dataset.nav);
    return;
  }

  const toastButton = event.target.closest("[data-toast]");
  if (toastButton) {
    showToast(toastButton.dataset.toast, "提示");
  }
});

resourceGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-buy-resource]");
  if (button) openQuote(button.dataset.buyResource);
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((item) => {
      const active = item === chip;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    renderResources(chip.dataset.filter);
  });
});

function sanitizeOrder(value) {
  if (!value || typeof value !== "object") return null;
  const resource = resources.find((item) => item.id === String(value.resourceId));
  if (!resource) return null;

  const quantity = Number(value.quantity);
  const hours = Number(value.hours);
  const status = allowedStatuses.has(value.status) ? value.status : "待确认";
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 99) return null;
  if (!Number.isInteger(hours) || hours < 1 || hours > 8760) return null;

  return {
    id: String(value.id).slice(0, 32),
    resourceId: resource.id,
    resourceName: displayResource(resource).name,
    region: String(value.region).slice(0, 20),
    quantity,
    hours,
    start: String(value.start).slice(0, 10),
    mode: value.mode === "长期使用" ? "长期使用" : "使用",
    delivery: value.delivery === "人工确认" ? "人工确认" : "标准服务",
    status,
    createdAt: String(value.createdAt).slice(0, 32),
  };
}

function loadOrders() {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(sanitizeOrder).filter(Boolean).slice(0, 50);
  } catch {
    return [];
  }
}

function saveOrders() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(orders.slice(0, 50)));
    return true;
  } catch {
    showToast("浏览器无法保存本地记录，本次操作只在当前页面有效。", "保存失败", true);
    return false;
  }
}

function renderOrders() {
  orderTableBody.replaceChildren();
  const hasOrders = orders.length > 0;
  orderEmpty.hidden = hasOrders;
  tableScroll.hidden = !hasOrders;
  orderCount.textContent = `共 ${orders.length} 条本地记录`;

  orders.forEach((order) => {
    const row = document.createElement("tr");
    const values = [order.id, order.resourceName, `${order.quantity} 台`, `${order.hours} 小时`];
    values.forEach((value) => row.append(createElement("td", "", value)));

    const statusCell = document.createElement("td");
    statusCell.append(createElement("span", `badge${order.status === "已取消" ? " cancelled" : ""}`, order.status));
    row.append(statusCell);

    const actionCell = document.createElement("td");
    const repeatButton = createElement("button", "table-action", displayText("再次提交"));
    repeatButton.type = "button";
    repeatButton.dataset.repeatOrder = order.id;
    actionCell.append(repeatButton);

    if (order.status !== "已取消") {
      const cancelButton = createElement("button", "table-action danger", displayText("取消记录"));
      cancelButton.type = "button";
      cancelButton.dataset.cancelOrder = order.id;
      actionCell.append(cancelButton);
    }

    row.append(actionCell);
    orderTableBody.append(row);
  });
}

orderTableBody.addEventListener("click", (event) => {
  const cancelButton = event.target.closest("[data-cancel-order]");
  if (cancelButton) {
    const order = orders.find((item) => item.id === cancelButton.dataset.cancelOrder);
    if (order) {
      order.status = "已取消";
      saveOrders();
      renderOrders();
      updateScheduleOptions();
      showToast(displayText("本地需求记录已取消。"), "操作成功");
    }
    return;
  }

  const repeatButton = event.target.closest("[data-repeat-order]");
  if (repeatButton) {
    const order = orders.find((item) => item.id === repeatButton.dataset.repeatOrder);
    if (order) repeatOrder(order);
  }
});

clearOrdersButton.addEventListener("click", () => {
  if (!orders.length) {
    showToast("当前没有可清空的本地记录。", "提示");
    return;
  }
  orders = [];
  saveOrders();
  renderOrders();
  updateScheduleOptions();
  showToast(displayText("本地需求记录已清空。"), "操作成功");
});

function repeatOrder(order) {
  quoteResource.value = order.resourceId;
  document.querySelector("#quoteRegion").value = order.region;
  document.querySelector("#quoteQuantity").value = String(order.quantity);
  document.querySelector("#quoteHours").value = String(order.hours);
  document.querySelector("#quoteStart").value = order.start;
  document.querySelector("#quoteMode").value = order.mode;
  const delivery = quoteForm.querySelector(`input[name="delivery"][value="${order.delivery}"]`);
  if (delivery) delivery.checked = true;
  showView("quote");
  showToast(displayText("已带入上一条本地需求，可调整后再次提交。"), displayText("再次提交"));
}

function updateScheduleOptions() {
  scheduleCurrent.replaceChildren();
  const activeOrders = orders.filter((order) => order.status !== "已取消");
  if (!activeOrders.length) {
    scheduleCurrent.add(new Option(displayText("请先创建本地需求记录"), ""));
    return;
  }

  activeOrders.forEach((order) => {
    const summary = showcaseMode
      ? `${order.resourceName} / ${order.quantity} 台 / ${order.hours} 小时`
      : `${order.resourceName} · ${order.quantity} 台 · ${order.hours} 小时`;
    scheduleCurrent.add(new Option(summary, order.id));
  });
}

function clearFieldError(field) {
  field.classList.remove("invalid");
  field.removeAttribute("aria-invalid");
  const error = document.querySelector(`[data-error-for="${field.id}"]`);
  if (error) error.textContent = "";
}

function setFieldError(field, message) {
  field.classList.add("invalid");
  field.setAttribute("aria-invalid", "true");
  const error = document.querySelector(`[data-error-for="${field.id}"]`);
  if (error) error.textContent = message;
}

function validateRequiredFields(form) {
  let firstInvalid;
  form.querySelectorAll("[required]").forEach((field) => {
    clearFieldError(field);
    let message = "";

    if (field.type === "checkbox" && !field.checked) message = "请先勾选此项";
    else if (!String(field.value).trim()) message = "请填写或选择此项";
    else if (field.type === "number") {
      const value = Number(field.value);
      const min = Number(field.min || 1);
      const max = field.max ? Number(field.max) : 8760;
      if (!Number.isInteger(value) || value < min || value > max) message = `请输入 ${min} 到 ${max} 的整数`;
    }
    else if (field.type === "date" && field.min && field.value < field.min) message = "开始日期不能早于今天";

    if (message) {
      setFieldError(field, message);
      firstInvalid ??= field;
    }
  });
  return firstInvalid;
}

document.querySelectorAll(".field input, .field select, .consent-row input").forEach((field) => {
  field.addEventListener("input", () => clearFieldError(field));
  field.addEventListener("change", () => clearFieldError(field));
});

quoteForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const firstInvalid = validateRequiredFields(quoteForm);
  if (firstInvalid) {
    firstInvalid.focus();
    showToast(displayText("请先完成标记的需求信息。"), "无法提交", true);
    return;
  }

  const formData = new FormData(quoteForm);
  const resource = resources.find((item) => item.id === formData.get("resource"));
  if (!resource) return;

  const order = {
    id: `ZTW-${Date.now().toString(36).toUpperCase()}`,
    resourceId: resource.id,
    resourceName: displayResource(resource).name,
    region: String(formData.get("region")),
    quantity: Number(formData.get("quantity")),
    hours: Number(formData.get("hours")),
    start: String(formData.get("start")),
    mode: String(formData.get("mode")),
    delivery: String(formData.get("delivery")),
    status: "待确认",
    createdAt: new Date().toISOString(),
  };

  orders.unshift(order);
  orders = orders.slice(0, 50);
  saveOrders();
  renderOrders();
  updateScheduleOptions();
  openOrderModal(order);
});

scheduleForm.addEventListener("submit", (event) => {
  event.preventDefault();
  let firstInvalid = validateRequiredFields(scheduleForm);
  const currentOrder = orders.find((order) => order.id === scheduleCurrent.value);
  if (!firstInvalid && currentOrder?.resourceId === scheduleTarget.value) {
    setFieldError(scheduleTarget, "目标资源不能与当前资源相同");
    firstInvalid = scheduleTarget;
  }
  if (firstInvalid) {
    firstInvalid.focus();
    showToast(displayText("请先完成标记的适配信息。"), "无法提交", true);
    return;
  }
  showToast(displayText("本地适配需求已生成，未发送到服务器。"), "操作成功");
});

supplierForm.addEventListener("submit", (event) => {
  event.preventDefault();
  let firstInvalid = validateRequiredFields(supplierForm);
  const startField = document.querySelector("#supplierStart");
  const endField = document.querySelector("#supplierEnd");

  if (!firstInvalid && new Date(startField.value) >= new Date(endField.value)) {
    setFieldError(endField, "结束时间必须晚于开始时间");
    firstInvalid = endField;
  }
  if (firstInvalid) {
    firstInvalid.focus();
    showToast("请先完成标记的资源信息。", "无法提交", true);
    return;
  }

  showToast(displayText("本地合作申请已生成，未发送到服务器。"), "操作成功");
  supplierForm.reset();
  setSupplierDateDefaults();
});

function appendSummary(label, value) {
  const row = document.createElement("div");
  row.append(createElement("dt", "", label), createElement("dd", "", value));
  orderSummary.append(row);
}

function openOrderModal(order) {
  lastModalFocus = document.activeElement;
  orderSummary.replaceChildren();
  appendSummary(displayText("记录编号"), order.id);
  appendSummary(displayText("资源信息"), order.resourceName);
  appendSummary(displayText("需求内容"), `${order.quantity} 台，${order.hours} 小时`);
  appendSummary("开始日期", order.start);
  appendSummary("当前状态", order.status);
  orderModal.hidden = false;
  document.body.classList.add("modal-open");
  inertTargets.forEach((element) => {
    element.inert = true;
  });
  orderModal.querySelector(".modal-close").focus();
}

function closeOrderModal(restoreFocus = true) {
  if (orderModal.hidden) return;
  orderModal.hidden = true;
  document.body.classList.remove("modal-open");
  inertTargets.forEach((element) => {
    element.inert = false;
  });
  if (restoreFocus && lastModalFocus instanceof HTMLElement) lastModalFocus.focus();
}

orderModal.querySelectorAll("[data-modal-close]").forEach((button) => {
  button.addEventListener("click", () => closeOrderModal());
});

viewOrderButton.addEventListener("click", () => {
  closeOrderModal(false);
  showView("manage");
});

document.addEventListener("keydown", (event) => {
  if (orderModal.hidden) return;

  if (event.key === "Escape") {
    closeOrderModal();
    return;
  }

  if (event.key === "Tab") {
    const focusable = Array.from(modalCard.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
      .filter((element) => !element.hidden && element.getClientRects().length > 0);
    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !modalCard.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
});

function showToast(message, title = "操作成功", isError = false) {
  window.clearTimeout(toastTimer);
  toastTitle.textContent = displayText(title);
  toastMessage.textContent = displayText(message);
  toastElement.classList.toggle("is-error", isError);
  toastElement.classList.add("show");
  toastTimer = window.setTimeout(() => toastElement.classList.remove("show"), 2600);
}

function localDateValue(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function localDateTimeValue(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
}

function setSupplierDateDefaults() {
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  document.querySelector("#supplierStart").value = localDateTimeValue(start);
  document.querySelector("#supplierEnd").value = localDateTimeValue(end);
}

function initialize() {
  renderResources();
  populateResourceSelects();
  renderOrders();
  updateScheduleOptions();

  const today = localDateValue(new Date());
  const quoteStart = document.querySelector("#quoteStart");
  quoteStart.min = today;
  quoteStart.value = today;
  setSupplierDateDefaults();
  showView("resources", { scroll: false, focusHeading: false });
}

initialize();
