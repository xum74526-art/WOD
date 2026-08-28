"use client";

import { useEffect, useMemo, useState } from "react";
import { CaretDown, CaretUp, Funnel, List, MagnifyingGlass, SquaresFour, X } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { ProductImage } from "@/components/product-image";

type GpuItem = {
  gpu_model: string; tier?: string; vram_gb?: number;
  min_price: number; median_price: number;
  official_min_price?: number; official_median_price?: number; official_available?: number;
  has_current_offers: boolean; offer_count: number; provider_count?: number; representative_offer_id?: string;
  region?: string; reliability?: number; gpu_count?: number; cpu_cores?: number; ram_gb?: number; disk_gb?: number;
  image_url?: string | null;
};
type CatalogResponse = { data?: GpuItem[]; meta?: { observed_at?: string; count?: number } };
type Filters = { model: string; vram: string; gpuCount: string; minPrice: string; maxPrice: string; region: string; availability: "all" | "available" | "unavailable" };
type SortKey = "recommended" | "latest" | "value" | "price";
type ViewMode = "cards" | "list";

const EMPTY_FILTERS: Filters = { model: "", vram: "", gpuCount: "", minPrice: "", maxPrice: "", region: "", availability: "all" };
const PAGE_SIZE = 12;
const SORTS: Array<{ key: SortKey; label: string; defaultDirection: "asc" | "desc" }> = [
  { key: "recommended", label: "综合推荐", defaultDirection: "desc" },
  { key: "latest", label: "最新更新", defaultDirection: "desc" },
  { key: "value", label: "性价比", defaultDirection: "desc" },
  { key: "price", label: "价格", defaultDirection: "asc" },
];

function normalizeSearch(value: string) {
  return value.toLowerCase().replace(/显存|vram/g, "").replace(/gb/g, "g").replace(/\s+/g, "").trim();
}
function priceOf(item: GpuItem) { return item.official_min_price ?? item.min_price; }
function medianOf(item: GpuItem) { return item.official_median_price ?? item.median_price; }
function formatPrice(value: number) { return value.toFixed(3); }
function FilterPanel(props: {
  filters: Filters; setFilters: (value: Filters) => void; models: string[]; vrams: number[]; counts: number[]; regions: string[]; close?: () => void;
}) {
  const { filters, setFilters, models, vrams, counts, regions, close } = props;
  const update = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters({ ...filters, [key]: value });
  return <div className="market-filter-panel">
    <div className="market-filter-panel__head"><strong>筛选资源</strong>{close && <button type="button" onClick={close} aria-label="关闭筛选"><X size={18} /></button>}</div>
    <label><span>GPU 型号</span><select value={filters.model} onChange={(event) => update("model", event.target.value)}><option value="">全部</option>{models.map((model) => <option value={model} key={model}>{model}</option>)}</select></label>
    <label><span>显存</span><select value={filters.vram} onChange={(event) => update("vram", event.target.value)}><option value="">全部</option>{vrams.map((vram) => <option value={vram} key={vram}>{vram}GB</option>)}</select></label>
    <label><span>GPU 数量</span><select value={filters.gpuCount} onChange={(event) => update("gpuCount", event.target.value)}><option value="">全部</option>{counts.map((count) => <option value={count} key={count}>{count} GPU</option>)}</select></label>
    <fieldset><legend>价格区间（卡时）</legend><div className="market-price-range"><input inputMode="decimal" value={filters.minPrice} onChange={(event) => update("minPrice", event.target.value)} placeholder="最低" /><span>—</span><input inputMode="decimal" value={filters.maxPrice} onChange={(event) => update("maxPrice", event.target.value)} placeholder="最高" /></div></fieldset>
    <label><span>供应商国家</span><select value={filters.region} onChange={(event) => update("region", event.target.value)}><option value="">全部</option>{regions.map((region) => <option value={region} key={region}>{region}</option>)}</select></label>
    <label><span>可用状态</span><select value={filters.availability} onChange={(event) => update("availability", event.target.value as Filters["availability"])}><option value="all">全部</option><option value="available">当前可用</option><option value="unavailable">暂无资源</option></select></label>
    <button className="market-filter-clear" type="button" onClick={() => setFilters(EMPTY_FILTERS)}>清空筛选</button>
  </div>;
}

export function MarketBrowser() {
  const [items, setItems] = useState<GpuItem[]>([]);
  const [selected, setSelected] = useState<GpuItem | null>(null);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("recommended");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [view, setView] = useState<ViewMode>("cards");
  const [page, setPage] = useState(1);
  const [filterOpen, setFilterOpen] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [targetGpu, setTargetGpu] = useState("");

  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get("gpu") ?? "";
    if (target) { setTargetGpu(target); setQuery(target); }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetch(apiBaseUrl + "/api/v1/public/market/summary", { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); return response.json(); })
      .then((payload: CatalogResponse) => { setItems(payload.data ?? []); setObservedAt(payload.meta?.observed_at ?? ""); setState("ready"); })
      .catch((reason) => { if (reason instanceof DOMException && reason.name === "AbortError") return; setMessage(reason instanceof Error ? reason.message : "市场服务不可用"); setState("error"); });
    return () => controller.abort();
  }, []);

  const models = useMemo(() => [...new Set(items.map((item) => item.gpu_model))].sort(), [items]);
  const vrams = useMemo(() => [...new Set(items.map((item) => item.vram_gb).filter((v): v is number => Boolean(v)))].sort((a, b) => a - b), [items]);
  const counts = useMemo(() => [...new Set(items.map((item) => item.gpu_count).filter((v): v is number => Boolean(v)))].sort((a, b) => a - b), [items]);
  const regions = useMemo(() => [...new Set(items.map((item) => item.region).filter((v): v is string => Boolean(v)))].sort(), [items]);
  const availableCount = items.filter((item) => item.has_current_offers).length;

  const filtered = useMemo(() => {
    const needle = normalizeSearch(query);
    const min = Number.parseFloat(filters.minPrice);
    const max = Number.parseFloat(filters.maxPrice);
    return items.filter((item) => {
      const memory = item.vram_gb ? String(item.vram_gb) + "g" : "";
      if (needle && !normalizeSearch(item.gpu_model + " " + (item.tier ?? "") + " " + memory).includes(needle)) return false;
      if (filters.model && item.gpu_model !== filters.model) return false;
      if (filters.vram && item.vram_gb !== Number(filters.vram)) return false;
      if (filters.gpuCount && item.gpu_count !== Number(filters.gpuCount)) return false;
      if (!Number.isNaN(min) && priceOf(item) < min) return false;
      if (!Number.isNaN(max) && priceOf(item) > max) return false;
      if (filters.region && item.region !== filters.region) return false;
      if (filters.availability === "available" && !item.has_current_offers) return false;
      if (filters.availability === "unavailable" && item.has_current_offers) return false;
      return true;
    });
  }, [items, query, filters]);

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    let result = 0;
    if (sortKey === "recommended") result = Number(a.has_current_offers) * 100000 + (a.official_available ?? 0) - (Number(b.has_current_offers) * 100000 + (b.official_available ?? 0));
    if (sortKey === "latest") result = (a.representative_offer_id ?? "").localeCompare(b.representative_offer_id ?? "");
    if (sortKey === "value") result = ((a.vram_gb ?? 0) / Math.max(priceOf(a), .0001)) - ((b.vram_gb ?? 0) / Math.max(priceOf(b), .0001));
    if (sortKey === "price") result = priceOf(a) - priceOf(b);
    if (!result) result = a.gpu_model.localeCompare(b.gpu_model);
    return direction === "asc" ? result : -result;
  }), [filtered, sortKey, direction]);

  const chips = useMemo(() => {
    const result: Array<{ key: keyof Filters; label: string }> = [];
    if (filters.model) result.push({ key: "model", label: filters.model });
    if (filters.vram) result.push({ key: "vram", label: filters.vram + "GB 显存" });
    if (filters.gpuCount) result.push({ key: "gpuCount", label: filters.gpuCount + " GPU" });
    if (filters.minPrice) result.push({ key: "minPrice", label: "最低 " + filters.minPrice + " 卡时" });
    if (filters.maxPrice) result.push({ key: "maxPrice", label: "最高 " + filters.maxPrice + " 卡时" });
    if (filters.region) result.push({ key: "region", label: filters.region });
    if (filters.availability !== "all") result.push({ key: "availability", label: filters.availability === "available" ? "当前可用" : "暂无资源" });
    return result;
  }, [filters]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageItems = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageNumbers = Array.from({ length: pageCount }, (_, index) => index + 1);

  useEffect(() => { setPage(1); }, [query, filters, sortKey, direction, view]);
  useEffect(() => {
    if (!targetGpu || state !== "ready") return;
    const frame = window.requestAnimationFrame(() => document.getElementById("gpu-market-" + targetGpu)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    return () => window.cancelAnimationFrame(frame);
  }, [targetGpu, state]);

  const updateSort = (key: SortKey) => {
    if (key === sortKey) setDirection((current) => current === "asc" ? "desc" : "asc");
    else { setSortKey(key); setDirection(SORTS.find((item) => item.key === key)!.defaultDirection); }
  };

  const changePage = (nextPage: number) => {
    setPage(Math.max(1, Math.min(pageCount, nextPage)));
    window.requestAnimationFrame(() => document.querySelector(".market-result-toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return <section className="data-browser market-catalog">
    <div className="market-top-controls"><div className="market-search-row"><label><MagnifyingGlass size={20} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 GPU 型号或显存，例如 RTX 4090、H100、80GB" />{query && <button type="button" onClick={() => { setQuery(""); setTargetGpu(""); }} aria-label="清空搜索"><X size={16} /></button>}</label><button className="market-mobile-filter" type="button" onClick={() => setFilterOpen(true)}><Funnel size={17} />筛选{chips.length ? " (" + chips.length + ")" : ""}</button></div>
    <div className="market-supply-readout"><div><span>资源目录</span><strong>{items.length} 型号</strong></div><div><span>当前供给</span><strong>{availableCount} 可租</strong></div><div className="market-supply-track" aria-label={`${items.length} 种 GPU 中 ${availableCount} 种当前可租`}><i style={{ width: items.length ? `${(availableCount / items.length) * 100}%` : "0%" }} /></div></div></div>
    {state === "loading" && <div className="data-empty">正在读取 GPU 市场目录</div>}
    {state === "error" && <div className="data-empty data-empty--error">{message}</div>}
    {state === "ready" && <div className="market-results-layout">
      <aside className="market-filter-sidebar"><FilterPanel filters={filters} setFilters={setFilters} models={models} vrams={vrams} counts={counts} regions={regions} /></aside>
      <div className="market-results">
        {chips.length > 0 && <div className="market-active-filters"><span>已选择</span>{chips.map((chip) => <button type="button" key={chip.key} onClick={() => setFilters({ ...filters, [chip.key]: chip.key === "availability" ? "all" : "" })}>{chip.label}<X size={12} /></button>)}<button className="clear-all" type="button" onClick={() => setFilters(EMPTY_FILTERS)}>全部清空</button></div>}
        <div className="market-result-toolbar"><strong>找到 {sorted.length} 种 GPU</strong><div className="market-sort-tabs">{SORTS.map((sort) => <button className={sortKey === sort.key ? "is-active" : ""} type="button" onClick={() => updateSort(sort.key)} key={sort.key}>{sort.label}{sortKey === sort.key ? direction === "asc" ? <CaretUp size={12} /> : <CaretDown size={12} /> : null}</button>)}</div><div className="market-view-switch"><button className={view === "cards" ? "is-active" : ""} type="button" onClick={() => setView("cards")} aria-label="卡片视图"><SquaresFour size={17} /></button><button className={view === "list" ? "is-active" : ""} type="button" onClick={() => setView("list")} aria-label="列表视图"><List size={18} /></button></div></div>
        {sorted.length === 0 && <div className="data-empty"><strong>当前没有匹配结果</strong><p>可以减少筛选条件，或者重新搜索 GPU 型号与显存。</p><button className="secondary-action" type="button" onClick={() => { setFilters(EMPTY_FILTERS); setQuery(""); }}>清空搜索与筛选</button></div>}
        {sorted.length > 0 && view === "cards" && <div className="market-resource-grid">{pageItems.map((item) => <MarketCard item={item} observedAt={observedAt} targeted={targetGpu.toLowerCase() === item.gpu_model.toLowerCase()} onDetails={() => setSelected(item)} key={item.gpu_model} />)}</div>}
        {sorted.length > 0 && view === "list" && <MarketList items={pageItems} observedAt={observedAt} onDetails={setSelected} />}
        {sorted.length > 0 && <nav className="market-pagination" aria-label="市场分页"><span>第 {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, sorted.length)} 项，共 {sorted.length} 项</span><div><button type="button" disabled={page === 1} onClick={() => changePage(page - 1)}>上一页</button>{pageNumbers.map((number) => <button className={page === number ? "is-active" : ""} type="button" aria-current={page === number ? "page" : undefined} onClick={() => changePage(number)} key={number}>{number}</button>)}<button type="button" disabled={page === pageCount} onClick={() => changePage(page + 1)}>下一页</button></div></nav>}
      </div>
    </div>}
    {filterOpen && <div className="market-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFilterOpen(false); }}><aside><FilterPanel filters={filters} setFilters={setFilters} models={models} vrams={vrams} counts={counts} regions={regions} close={() => setFilterOpen(false)} /><button className="market-filter-apply" type="button" onClick={() => setFilterOpen(false)}>查看 {filtered.length} 个结果</button></aside></div>}
    {selected && <MarketDetail item={selected} observedAt={observedAt} close={() => setSelected(null)} />}
  </section>;
}

function MarketCard({ item, observedAt, targeted, onDetails }: { item: GpuItem; observedAt: string; targeted: boolean; onDetails: () => void }) {
  return <article id={"gpu-market-" + item.gpu_model} className={"market-resource-card" + (item.has_current_offers ? "" : " is-unavailable") + (targeted ? " is-targeted" : "")}>
    <header><ProductImage imageUrl={item.image_url} gpuModel={item.gpu_model}/><div><h2>{item.gpu_model}</h2><p>{item.vram_gb ? item.vram_gb + "GB 显存" : "显存待补充"} · {item.gpu_count ?? "—"} GPU</p></div><span>{item.has_current_offers ? "可用" : "暂无资源"}</span></header>
    <div className="market-resource-price"><small>当前最低价</small><strong>{formatPrice(priceOf(item))}</strong><span>卡时 / GPU·小时</span><p>市场中位价 {formatPrice(medianOf(item))} 卡时</p></div>
    <dl><div><dt>供应商国家</dt><dd>{item.region || "暂无"}</dd></div><div><dt>可用资源</dt><dd>{item.has_current_offers ? item.offer_count + " 个报价 / " + (item.provider_count ?? 0) + " 家" : "0"}</dd></div><div><dt>更新时间</dt><dd>{observedAt ? new Date(observedAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}</dd></div></dl>
    <button type="button" disabled={!item.has_current_offers} onClick={onDetails}>{item.has_current_offers ? "查看详情" : "暂无资源"}</button>
  </article>;
}

function MarketList({ items, observedAt, onDetails }: { items: GpuItem[]; observedAt: string; onDetails: (item: GpuItem) => void }) {
  return <div className="market-resource-table"><div className="market-resource-table__head"><span>GPU</span><span>显存</span><span>数量</span><span>供应商国家</span><span>最低价</span><span>中位价</span><span>更新时间</span><span>可用资源</span><span>操作</span></div>{items.map((item) => <article className={!item.has_current_offers ? "is-unavailable" : ""} key={item.gpu_model}><span><strong>{item.gpu_model}</strong><small>{item.tier || "GPU"}</small></span><span>{item.vram_gb ? item.vram_gb + "GB" : "—"}</span><span>{item.gpu_count ?? "—"}</span><span>{item.region || "—"}</span><span><strong>{formatPrice(priceOf(item))}</strong><small>卡时</small></span><span>{formatPrice(medianOf(item))}</span><span>{observedAt ? new Date(observedAt).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) : "—"}</span><span>{item.has_current_offers ? item.offer_count : 0}</span><button type="button" disabled={!item.has_current_offers} onClick={() => onDetails(item)}>{item.has_current_offers ? "详情" : "暂无"}</button></article>)}</div>;
}

function MarketDetail({ item, observedAt, close }: { item: GpuItem; observedAt: string; close: () => void }) {
  return <div className="market-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="market-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="market-detail-title"><button className="market-detail-close" type="button" onClick={close} aria-label="关闭"><X size={18} /></button><p className="hero-eyebrow">KAI PRICING MARKET</p><ProductImage imageUrl={item.image_url} gpuModel={item.gpu_model}/><h2 id="market-detail-title">{item.gpu_model}</h2><p>{item.vram_gb}GB 显存 · {item.gpu_count ?? "—"} GPU</p><dl><div><dt>当前最低价</dt><dd>{formatPrice(priceOf(item))} 卡时 / GPU·小时</dd></div><div><dt>供应商加权中位价</dt><dd>{formatPrice(medianOf(item))} 卡时 / GPU·小时</dd></div><div><dt>可用资源</dt><dd>{item.offer_count} 个报价 / {item.provider_count ?? 0} 家供应商</dd></div><div><dt>供应商国家</dt><dd>{item.region || "地区待确认"}</dd></div><div><dt>CPU / 内存</dt><dd>{item.cpu_cores ?? "—"} 核 / {item.ram_gb ?? "—"}GB</dd></div><div><dt>硬盘</dt><dd>{item.disk_gb ?? "—"}GB</dd></div><div><dt>更新时间</dt><dd>{observedAt ? new Date(observedAt).toLocaleString("zh-CN") : "—"}</dd></div><div><dt>数据用途</dt><dd>KAI 行情比较与趋势展示</dd></div></dl></section></div>;
}
