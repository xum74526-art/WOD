"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

export type KaiLocale = "zh-CN" | "en";

const english: Record<string, string> = {
  "language.switchEnglish": "Switch to English",
  "language.switchChinese": "切换到中文",
  "theme.light": "Light mode",
  "theme.dark": "Dark mode",
  "theme.toLight": "Switch to light mode",
  "theme.toDark": "Switch to dark mode",
  "nav.home": "Home",
  "nav.market": "Compute Market",
  "nav.trends": "Market Trends",
  "nav.community": "Community",
  "nav.supplierApply": "Become a Supplier",
  "nav.download": "Download App",
  "nav.personalCenter": "My Account",
  "nav.supplierConsole": "Supplier Console",
  "nav.adminConsole": "Admin Console",
  "nav.accountOverview": "Account Overview",
  "nav.orders": "My Orders",
  "nav.assets": "My Assets",
  "nav.wallet": "Wallet & Ledger",
  "nav.accountSecurity": "Account & Security",
  "nav.supplierOverview": "Supplier Overview",
  "nav.deliveryOrders": "Delivery Orders",
  "nav.personalAccount": "Personal Account",
  "nav.adminOverview": "Admin Overview",
  "nav.register": "Sign up",
  "nav.login": "Sign in",
  "nav.logout": "Sign out",
  "nav.openAccount": "Open account shortcuts",
  "footer.description": "KAI Future Compute Center connects institutional demand, capacity suppliers, and verifiable compute delivery.",
  "footer.disclaimer": "© 2026 KAI. Services and specifications are subject to the effective service documents.",
  "footer.product": "Product",
  "footer.ecosystem": "Ecosystem",
  "footer.company": "Company",
  "footer.support": "Support",
  "footer.assets": "My Assets",
  "footer.requests": "Requests & Quotes",
  "footer.about": "About KAI",
  "footer.contact": "Contact Us",
  "footer.help": "Help Center",
  "footer.terms": "Terms of Service",
  "footer.privacy": "Privacy Notice",
  "home.title": "GPU servers,\nready on demand",
  "home.description": "Compare GPU models, configurations, and hourly prices transparently. After payment, KAI authorizes your SSH public key so you can connect with one command.",
  "home.step1.title": "Choose a server",
  "home.step1.desc": "Compare GPU, VRAM, region, and hourly price",
  "home.step2.title": "Submit your SSH public key",
  "home.step2.desc": "Only your public key is sent after payment; private keys never enter KAI",
  "home.step3.title": "Copy the connection command",
  "home.step3.desc": "The Agent authorizes access automatically and revokes it at expiry",
  "home.browse": "Browse GPU Servers",
  "home.publish": "List a Server",
  "home.assurance1": "Transparent hourly billing",
  "home.assurance2": "Automatic SSH key authorization",
  "home.assurance3": "Automatic access revocation",
  "home.community.title": "Compute Community",
  "home.community.desc": "Follow GPU, AI infrastructure, and compute-market updates.",
  "home.community.action": "Open Community",
  "home.requests.title": "Public Requests",
  "home.requests.desc": "Buyers publish GPU and server requirements; suppliers respond with matching capacity.",
  "home.requests.action": "View Request Market",
  "home.cta.kicker": "Have idle servers?",
  "home.cta.title": "Register your server and connect the KAI Agent",
  "home.cta.desc": "After server and Agent review, KAI publishes the listing and authorizes buyer public keys automatically—no password sharing required.",
  "home.cta.action": "Apply as Supplier",
  "market.title": "Compute Market",
  "market.description": "Choose verified compute resources with an online Agent and rent them by the hour using your own SSH public key.",
  "market.shared": "Shared Compute Resources",
  "market.source": "KAI Pricing",
  "market.loading": "Loading supplier resources…",
  "market.empty": "No published resources yet",
  "market.emptyDesc": "Approved supplier resources will appear here automatically.",
  "market.manage": "Manage Servers",
  "market.review": "Review Servers",
  "market.view": "View Server",
  "market.rent": "View & Rent",
  "market.buy": "Buy Now",
  "market.details": "View Details",
  "market.available": "Available",
  "market.unavailable": "Unavailable",
  "market.region": "Region",
  "market.config": "Configuration",
  "market.hourly": "Hourly price",
  "product.rebate.label": "Estimated personal purchase rebate at expiry",
  "product.rebate.amount": "+{amount} card hours",
  "product.rebate.login": "Sign in to load your personal rebate tier.",
  "product.rebate.unavailable": "Your personal rebate policy could not be loaded. Please refresh shortly.",
  "product.rebate.disabled": "Personal purchase rebates are currently disabled.",
  "product.rebate.minimum": "Your current personal tier is {current}%. Personal purchase rebates apply to orders of at least {amount} card hours.",
  "product.rebate.capExhausted": "Your current tier is {current}% and the post-order estimate is {projected}%. Your monthly allowance is fully used, so this order's estimated rebate is 0.",
  "product.rebate.capLimited": "Your current tier is {current}% and the post-order estimate is {projected}%. The remaining monthly allowance limits this order's estimated rebate to {remaining} card hours.",
  "product.rebate.tierChange": "Your current personal tier is {current}%; after this order it is estimated to be {projected}%.",
  "product.rebate.tierStable": "Your current and estimated personal tier for this order is {rate}%.",
  "product.rebate.settlement": "This is an estimate. At delivery confirmation, the server recalculates it from your personal tier and remaining allowance; the final amount is settled when the asset expires.",
  "rebate.personal.title": "Personal Purchase Rebate",
  "rebate.personal.monthSpent": "Personal purchases this month",
  "rebate.personal.monthRebated": "Personal rebates this month",
  "rebate.personal.currentTier": "Current tier: {rate}%",
  "rebate.personal.currentTierLabel": "Current personal purchase tier",
  "rebate.personal.pending": "Pending expiry settlement (card hours)",
  "rebate.personal.noHint": "There is no new personal-tier update.",
  "rebate.personal.mechanism": "Only confirmed usage orders count. Your tier is based on personal card-hour purchases confirmed this month, and the rebate is credited when the asset term ends.",
  "rebate.personal.capProgress": "Entitled this month: {entitled} · Cap used: {used} · Remaining allowance: {remaining} · Monthly cap: {cap} card hours · {mode}",
  "rebate.personal.summary": "Pending at expiry: {pending} · Entitled this month: {entitled} · Cap used: {used} · Remaining allowance: {remaining} · Monthly cap: {cap} card hours",
  "rebate.personal.tiers": "Personal Purchase Tiers",
  "rebate.supplier.title": "Supplier Sales Rebate",
  "rebate.supplier.monthSales": "Confirmed sales this month",
  "rebate.supplier.monthRebated": "Supplier sales rebates this month",
  "rebate.supplier.currentTierLabel": "Current supplier sales tier",
  "rebate.supplier.noHint": "There is no new supplier-tier update.",
  "rebate.supplier.mechanism": "The rebate base is the total card hours from confirmed sales this month—not the platform service fee. The rebate equals confirmed sales multiplied by the current tier rate.",
  "rebate.supplier.summary": "Estimated rebate: {estimated} · Entitled this month: {entitled} · Cap used: {used} · Remaining allowance: {remaining} · Monthly cap: {cap} card hours",
  "rebate.supplier.tiers": "Supplier Sales Tiers",
  "rebate.unit.cardHours": "card hours",
  "rebate.current": "Current",
  "rebate.mode.live": "live card hours",
  "rebate.mode.cardHours": "in-app card hours",
  "rebate.mode.disabled": "disabled",
  "rebate.center.title": "Rebate Center",
  "rebate.center.description": "Review personal purchase rebates and supplier sales rebates separately, with independent tiers and progress.",
  "support.title": "Help & Support",
  "support.connecting": "Connecting to support…",
  "support.selfServiceOnline": "Self-service support is online. Ask common questions or create a support ticket.",
  "support.aiOnline": "Smart support is online. Ask common questions or create a support ticket.",
  "support.loginTitle": "Sign in to use online support",
  "support.loginDescription": "Support conversations and tickets are saved to your account.",
  "support.loginAction": "Sign in",
  "support.error": "The support request could not be completed. Please retry.",
  "support.me": "Me",
  "support.assistant": "KAI Self-service Support",
  "support.createTicket": "Create support ticket",
  "support.welcome": "Hello, how can we help?",
  "support.welcomeDescription": "Ask about recharges, withdrawals, orders, devices, or your account.",
  "support.inputPlaceholder": "Enter your question…",
  "support.sending": "Sending",
  "support.send": "Send",
  "support.myTickets": "My tickets",
  "support.subject": "Subject",
  "support.description": "Description",
  "support.category": "Category",
  "support.category.order": "Orders",
  "support.category.payment": "Payments",
  "support.category.device": "Devices",
  "support.category.account": "Account",
  "support.category.other": "Other",
  "support.cancel": "Cancel",
  "support.submitTicket": "Submit ticket",
  "support.emptyTickets": "No support tickets yet",
  "support.status.pending": "Pending assignment",
  "support.status.assigned": "In progress",
  "support.status.resolved": "Resolved",
  "support.status.closed": "Closed",
  "settings.title": "Account Settings",
  "settings.description": "Manage your username, avatar, password, and account role.",
  "settings.loading": "Loading account details…",
  "settings.error": "The account request could not be completed. Please retry.",
  "settings.avatarAlt": "Account avatar",
  "settings.uploading": "Uploading",
  "settings.changeAvatar": "Change avatar",
  "settings.unifiedAccount": "Unified account",
  "settings.phone": "Phone number",
  "settings.notBound": "Not linked",
  "settings.supplierReview": "Supplier review",
  "settings.supplierApproved": "Approved",
  "settings.supplierPending": "In review",
  "settings.supplierRejected": "Not approved",
  "settings.notApplied": "Not applied",
  "settings.profile": "Profile",
  "settings.username": "Username",
  "settings.phoneCredential": "Your phone number is the sign-in credential. Complete identity verification before changing it.",
  "settings.saving": "Saving…",
  "settings.saveProfile": "Save profile",
  "settings.changePassword": "Change password",
  "settings.currentPassword": "Current password",
  "settings.newPassword": "New password",
  "settings.confirmPassword": "Confirm new password",
  "settings.updating": "Updating…",
  "settings.updatePassword": "Update password",
  "settings.activeRole": "Active role",
  "settings.role.personal": "Personal user",
  "settings.role.supplier": "Supplier",
  "settings.role.admin": "Administrator",
  "settings.roleApprovedDescription": "Your supplier review is approved. You can switch between the personal and supplier workspaces.",
  "settings.rolePendingDescription": "The supplier workspace becomes available after supplier approval.",
  "settings.roleSwitched": "Account role switched",
  "settings.switching": "Switching…",
  "settings.switchPersonal": "Switch to personal user",
  "settings.switchSupplier": "Switch to supplier",
  "settings.kaiBinding": "Kai identity link",
  "settings.kaiBoundDescription": "This account is linked to Kai SSO and can use the same identity on Web, iOS, and Android.",
  "settings.kaiBindingDescription": "Link this KAI account to Kai SSO without creating a second business account.",
  "settings.processing": "Processing…",
  "settings.kaiBound": "Kai linked",
  "settings.bindKai": "Link Kai identity",
  "settings.kaiCanceled": "Kai identity linking was canceled",
  "settings.kaiFailed": "Kai identity linking failed. Please retry.",
  "settings.kaiBoundSuccess": "Kai identity linked. You can now sign in with Kai.",
  "settings.usernameMinimum": "Username must contain at least 2 characters",
  "settings.profileSaved": "Account profile saved",
  "settings.passwordMismatch": "The new passwords do not match",
  "settings.passwordUpdated": "Password updated",
  "settings.avatarLimit": "Avatar images must be 2 MB or smaller",
  "settings.avatarUpdated": "Avatar updated",
  "settings.kaiNoUrl": "Kai SSO did not return an authorization URL",
  "trends.title": "GPU Compute Market Trends",
  "trends.description": "Compare card-hour price movements and current market ranges across GPU models.",
  "community.title": "Understand compute before you choose",
  "community.description": "GPU pricing, hardware, infrastructure, and industry intelligence for better server purchasing and rental decisions.",
  "community.scope": "Coverage",
  "community.fourTopics": "Four intelligence themes",
  "community.topic.market": "Pricing & Supply",
  "community.topic.hardware": "GPU & Hardware",
  "community.topic.infrastructure": "Compute & Data Centers",
  "community.topic.industry": "Policy & Industry",
  "community.refresh": "Sources are checked for updates every 30 minutes",
  "auth.login.kicker": "WELCOME BACK",
  "auth.register.kicker": "CREATE YOUR ACCOUNT",
  "auth.login.title": "Welcome back",
  "auth.register.title": "Create account",
  "auth.login.desc": "Sign in to your unified account to access orders, assets, and wallet data.",
  "auth.register.desc": "Create one account for both Web and App, backed by the same data.",
  "auth.phone": "Phone number",
  "auth.password": "Password",
  "auth.setPassword": "Set password",
  "auth.nickname": "Display name",
  "auth.invite": "Invitation code (optional)",
  "auth.captcha": "Captcha",
  "auth.refreshCaptcha": "Refresh captcha",
  "auth.forgot": "Forgot password?",
  "auth.kai": "Kai SSO",
  "auth.login": "Sign in",
  "auth.register": "Create account",
  "auth.processing": "Processing…",
  "auth.termsPrefix": "I have read and agree to the",
  "auth.already": "Already have a KAI account?",
  "auth.new": "New to KAI?",
  "auth.backLogin": "Back to sign in",
  "auth.create": "Create account",
  "auth.help": "Sign-in help",
  "auth.role.buyer": "Buyer account",
  "auth.role.buyerDesc": "Manage SSH keys, server leases, and renewals",
  "auth.role.supplier": "Supplier account",
  "auth.role.supplierDesc": "Register servers, install the Agent, and manage leases",
  "auth.role.admin": "Admin account",
  "auth.role.adminDesc": "Review suppliers, servers, and platform health",
  "auth.intro.login": "Connect to your compute resources",
  "auth.intro.register": "Create your KAI account",
  "auth.intro.forgot": "Recover your KAI account",
  "auth.backMarket": "Back to Compute Market",
  "workspace.connected": "Connected to unified business platform",
  "workspace.publicSite": "Public Site",
  "workspace.buyer": "Buyer Center",
  "workspace.supplier": "Supplier Console",
  "workspace.admin": "Admin Console",
  "account.welcome": "Welcome back, {name}",
  "account.sameData": "Review orders, assets, and wallet data for your unified account.",
  "account.next": "Next steps",
};

// Compatibility dictionary for legacy Web screens. New and actively maintained
// components should use `t()` directly; this bridge keeps retained legacy pages
// usable in English without removing their original Chinese implementation.
const legacyEnglish: Record<string, string> = {
  "全部": "All", "热门": "Popular", "最新": "Latest", "推荐": "Recommended", "关注": "Following", "视频": "Video",
  "主导航": "Main navigation", "返回首页": "Back to home", "平台租用特性": "Platform rental features", "GPU 算力行情预览": "GPU market preview", "算力生态入口": "Compute ecosystem",
  "刷新": "Refresh", "搜索": "Search", "关闭": "Close", "取消": "Cancel", "确认": "Confirm", "保存": "Save", "删除": "Delete", "编辑": "Edit", "返回": "Back",
  "上一页": "Previous", "下一页": "Next", "详情": "Details", "暂无": "Unavailable", "加载中…": "Loading…", "处理中…": "Processing…",
  "发布动态": "Create post", "发布": "Publish", "发布中…": "Publishing…", "搜索动态、话题或作者": "Search posts, topics, or authors", "写下评论…": "Write a comment…", "发送": "Send",
  "条社区动态": "community posts", "当前没有动态": "No posts yet", "切换标签或发布第一条内容。": "Switch tabs or create the first post.",
  "GPU 型号": "GPU model", "观察周期": "Time range", "当前实时中位价": "Current live median", "当前价格": "Current price", "数据不足": "Insufficient data", "实时数据源": "Live sources",
  "正在生成价格 K 线": "Generating price chart", "正在加载算力行情": "Loading compute market", "正在读取真实历史价格。": "Loading real historical prices.",
  "涨幅榜": "Top gainers", "跌幅榜": "Top losers", "GPU 完整行情": "Full GPU market", "搜索完整行情": "Search full market", "全部显存": "All VRAM", "只看上涨": "Gainers only", "只看下跌": "Losers only",
  "当前价": "Current", "本周涨跌": "Weekly change", "4周涨跌": "4-week change", "3个月涨跌": "3-month change", "最高价": "High", "最低价": "Low", "更新时间": "Updated",
  "个人资产": "My Assets", "购买算力": "Buy Compute", "资产总值": "Total asset value", "运行中算力": "Running compute", "今日收益": "Today's earnings", "待续费": "Renewal due",
  "运行中": "Running", "已到期": "Expired", "已出售": "Sold", "待生效": "Pending", "当前分类没有资产": "No assets in this category", "进入算力市场": "Open Compute Market",
  "我的订单": "My Orders", "订单": "Orders", "待付款": "Awaiting payment", "处理中": "Processing", "已完成": "Completed", "已取消": "Cancelled", "立即购买": "Buy now", "暂不可购买": "Unavailable",
  "钱包流水": "Wallet ledger", "提现记录": "Withdrawals", "暂无钱包流水": "No wallet activity", "暂无提现记录": "No withdrawals", "充值": "Recharge", "提现": "Withdraw",
  "设备托管": "Device Hosting", "提交托管申请": "Submit hosting request", "申请记录": "Request history", "主体类型": "Entity type", "个人": "Individual", "企业": "Company", "联系人": "Contact", "联系电话": "Phone", "设备型号": "Device model", "设备数量": "Device count", "设备所在地": "Device location", "补充说明": "Additional notes",
  "收益与返佣": "Earnings & Rebates", "收益走势": "Earnings trend", "收益记录": "Earnings history", "返佣进度": "Rebate progress", "累计收益": "Total earnings",
  "银行卡": "Bank cards", "实名认证": "Identity verification", "通知中心": "Notifications", "在线客服": "Support", "地址管理": "Addresses", "账户设置": "Account settings",
  "求购与报价": "Requests & Quotes", "求购市场": "Request Market", "在线算力": "Online compute", "线下设备": "Offline devices", "发布求购": "Create request", "我的需求": "My requests", "可报价需求": "Open requests", "报价记录": "Quotes", "选择报价": "Select quote",
  "账户与安全": "Account & Security", "修改密码": "Change password", "退出登录": "Sign out", "深色模式": "Dark mode", "浅色模式": "Light mode",
  "商家后台": "Supplier Console", "经营总览": "Operations Overview", "算力商品": "Compute Products", "交付订单": "Delivery Orders", "经营统计": "Analytics", "商家资料": "Supplier Profile",
  "管理控制台": "Admin Console", "运营总览": "Admin Overview", "银行卡复核": "Bank Card Review", "提现结算": "Withdrawal Settlement",
  "暂无商品": "No products", "暂无已发布资源": "No published resources", "暂不可租": "Unavailable", "可下单": "Available", "已发布": "Published", "区域": "Region", "配置": "Configuration", "每小时价格": "Hourly price",
  "华北": "North China", "华东": "East China", "华中": "Central China", "华南": "South China", "西北": "Northwest China", "西南": "Southwest China", "东北": "Northeast China",
  "中国大陆": "Mainland China", "亚太": "Asia Pacific", "北美": "North America", "欧洲": "Europe", "中东": "Middle East", "南美": "South America", "非洲": "Africa", "海外": "Overseas", "全球/未披露": "Global / Undisclosed", "未披露": "Undisclosed", "未标注": "Not specified", "GPU·小时": "GPU·hour",
  "交付 AI 算力，构筑稳健未来。": "Deliver AI compute. Build a resilient future.",
  "交付 AI 算力，": "Deliver AI compute,", "构筑稳健未来。": "build a resilient future.",
  "北斗 kai 面向机构，统一不同供应商的模型服务标准，按指定时段协调容量，持续监测服务质量，并交付真实 Chat Completions 服务。": "KAI standardizes model services across suppliers, coordinates capacity for defined windows, monitors quality, and delivers real Chat Completions workloads for institutions.",
  "北斗 kai 的方法": "The KAI approach", "稳健算力，始于可预期的交付": "Reliable compute starts with predictable delivery", "把分散的模型服务容量整理成机构能够规划、比较及核对的服务，让算力从供应能力走向真实工作负载。": "We organize fragmented model capacity into services institutions can plan, compare, and verify—from available supply to real workloads.",
  "可预期": "Predictable", "按已指定的模型、版本、区域及服务时段安排容量。": "Capacity is scheduled by model, version, region, and service window.", "可比较": "Comparable", "以一致的服务参数及计量方式描述不同供应商的容量。": "Supplier capacity is described using consistent service parameters and metering.", "可验证": "Verifiable", "以 Chat Completions 用量及服务质量记录交付结果。": "Delivery is verified through Chat Completions usage and service-quality records.",
  "清晰分工，持续交付": "Clear ownership, continuous delivery", "机构客户、容量供应商及北斗 kai 运营团队各自承担清楚、可追溯的服务责任。": "Institutional clients, capacity suppliers, and KAI operations each own clear and traceable responsibilities.", "参与方": "Participant", "能力": "Capability", "责任": "Responsibility", "机构客户": "Institutional client", "容量供应商": "Capacity supplier", "北斗 kai 运营团队": "KAI operations",
  "规划下一段算力容量": "Plan your next compute capacity", "如贵机构正为指定模型、区域或时段规划容量，请联系北斗 kai。": "Contact KAI if your organization is planning capacity for a specific model, region, or time window.", "联系我们": "Contact Us",
  "规划下一段算力容量。": "Plan your next compute capacity.", "如贵机构正为指定模型、区域或时段规划容量，请联系北斗 kai。我们将根据需求与可用容量安排后续接入。": "Contact KAI if your organization is planning capacity for a specific model, region, or time window. We will arrange onboarding based on demand and available supply.", "机构接入": "Institutional Access", "这是北斗 kai 对外公布的机构接入联系邮箱。": "This is KAI's official email for institutional access.", "建议一并说明": "Please include", "模型与版本": "Model & version", "计划使用的模型和版本要求。": "Your required model and version.", "区域与时段": "Region & schedule", "服务区域、时区和计划使用时段。": "Service region, time zone, and planned usage window.", "容量需求": "Capacity requirements", "预期容量单位及服务目标。": "Expected capacity units and service objectives.",
  "规划下一段": "Plan your next", "算力容量。": "compute capacity.",
  "把算力市场装进口袋": "Put the compute market in your pocket", "网页与 App 使用同一个北斗 kai 账号、余额、订单和算力数据。选择你的设备开始使用。": "Web and App share the same KAI account, balance, orders, and compute data. Choose your device to get started.", "优先发布": "Priority release", "适用于 Android 8.0 及以上设备。可从本页直接下载安装，也可等待应用商店版本。": "For Android 8.0 and later. Download the APK directly from this page, or wait for the app-store release.", "下载 APK": "Download APK", "Android 应用商店": "Android app stores", "即将上线": "Coming soon", "版本": "Version", "大小": "Size", "架构": "Architecture", "等待上架": "Pending review", "待发布": "Pending release", "iOS 版本与 Android 共用业务能力。完成 Apple 审核后，将通过 App Store 正式提供。": "iOS and Android share the same business capabilities. The iOS app will be available through the App Store after Apple review.", "系统": "System", "渠道": "Channel", "只从北斗 kai 官方页面安装": "Install only from official KAI pages",
  "把算力市场": "Put the compute market", "装进口袋": "in your pocket",
};

function LegacyLocaleBridge({ locale }: { locale: KaiLocale }) {
  const originalText = useRef(new Map<Text, string>());
  const originalAttributes = useRef(new Map<Element, Map<string, string>>());
  useEffect(() => {
    const textEntries = originalText.current;
    const attributeEntries = originalAttributes.current;
    if (locale !== "en") {
      textEntries.forEach((value, node) => { if (node.isConnected) node.nodeValue = value; });
      attributeEntries.forEach((values, element) => { if (element.isConnected) values.forEach((value, name) => element.setAttribute(name, value)); });
      textEntries.clear();
      attributeEntries.clear();
      return;
    }
    const translateText = (node: Text) => {
      const raw = node.nodeValue || "";
      const trimmed = raw.trim();
      const translated = legacyEnglish[trimmed];
      if (!translated) return;
      textEntries.set(node, raw);
      node.nodeValue = raw.replace(trimmed, translated);
    };
    const translateElement = (element: Element) => {
      for (const name of ["placeholder", "title", "aria-label"]) {
        const raw = element.getAttribute(name);
        if (!raw || !legacyEnglish[raw]) continue;
        let values = attributeEntries.get(element);
        if (!values) { values = new Map(); attributeEntries.set(element, values); }
        values.set(name, raw);
        element.setAttribute(name, legacyEnglish[raw]);
      }
    };
    const translateTree = (root: Node) => {
      if (root.nodeType === Node.TEXT_NODE) { translateText(root as Text); return; }
      if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
      if (root.nodeType === Node.ELEMENT_NODE) translateElement(root as Element);
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
      let node = walker.nextNode();
      while (node) { if (node.nodeType === Node.TEXT_NODE) translateText(node as Text); else translateElement(node as Element); node = walker.nextNode(); }
    };
    translateTree(document.body);
    const observer = new MutationObserver((mutations) => mutations.forEach((mutation) => {
      if (mutation.type === "characterData") translateText(mutation.target as Text);
      mutation.addedNodes.forEach(translateTree);
    }));
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [locale]);
  return null;
}

type LocaleContextValue = {
  locale: KaiLocale;
  setLocale: (locale: KaiLocale) => void;
  toggleLocale: () => void;
  t: (key: string, fallback: string, values?: Record<string, string | number>) => string;
  dateLocale: string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleRoot({ initialLocale, children }: { initialLocale: KaiLocale; children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<KaiLocale>(initialLocale);
  const setLocale = useCallback((next: KaiLocale) => {
    setLocaleState(next);
    document.documentElement.lang = next;
    document.documentElement.dataset.locale = next;
    document.cookie = `kai.locale=${encodeURIComponent(next)}; Path=/; Max-Age=31536000; SameSite=Lax`;
    localStorage.setItem("kai.locale", next);
  }, []);
  const toggleLocale = useCallback(() => setLocale(locale === "en" ? "zh-CN" : "en"), [locale, setLocale]);
  const t = useCallback((key: string, fallback: string, values?: Record<string, string | number>) => {
    const template = locale === "en" ? english[key] || fallback : fallback;
    return Object.entries(values || {}).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), template);
  }, [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
  }, [locale]);
  const value = useMemo(() => ({ locale, setLocale, toggleLocale, t, dateLocale: locale === "en" ? "en-US" : "zh-CN" }), [locale, setLocale, toggleLocale, t]);
  return <LocaleContext.Provider value={value}><LegacyLocaleBridge locale={locale}/>{children}</LocaleContext.Provider>;
}

export function useI18n() {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("useI18n must be used inside LocaleRoot");
  return value;
}

export function I18nText({ id, zh, values }: { id: string; zh: string; values?: Record<string, string | number> }) {
  const { t } = useI18n();
  return <>{t(id, zh, values)}</>;
}
