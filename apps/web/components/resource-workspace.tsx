"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Cube, FloppyDisk, Plus, Trash } from "@phosphor-icons/react";
import { ApiError } from "@/lib/api";
import { createMobileSupplierDevice, deleteMobileSupplierDevice, listMobileSupplierDevices, updateMobileSupplierDevice, type MobileSupplierDevice, type MobileSupplierDeviceUpdate } from "@/lib/supplier-api";
import { errorMessage } from "@/lib/commerce-ui";
import { displayBusinessReference } from "@/lib/display-reference";

const blank = {
  name: "",
  gpu_model: "NVIDIA H100",
  memory: "80GB",
  price: "",
  stock: "1",
  region_code: "east_china",
  region_name: "华东",
  city: "上海",
  desc: "",
};

export function ResourceWorkspace() {
  const [rows, setRows] = useState<MobileSupplierDevice[]>([]);
  const [selected, setSelected] = useState<MobileSupplierDevice | null>(null);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (preferredId?: number) => {
    setError("");
    try {
      const items = await listMobileSupplierDevices("all");
      setRows(items);
      setSelected(items.find((item) => item.id === preferredId) || items[0] || null);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function startCreate() {
    setSelected(null);
    setEditing(true);
    setForm(blank);
  }

  function startEdit(item: MobileSupplierDevice) {
    setSelected(item);
    setEditing(true);
    setForm({
      ...blank,
      name: item.name,
      gpu_model: item.gpu_model,
      memory: item.memory,
      price: String(item.price),
      stock: String(item.stock),
      region_name: item.region,
      city: item.city,
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let id: number;
      if (selected) {
        const changes: MobileSupplierDeviceUpdate = {};
        const price = Number(form.price);
        const stock = Number(form.stock);
        if (form.name !== selected.name) changes.name = form.name;
        if (price !== selected.price) changes.price = price;
        if (stock !== selected.stock) changes.stock = stock;
        if (!Object.keys(changes).length) {
          setEditing(false);
          return;
        }
        const updated = await updateMobileSupplierDevice(selected.id, selected.version, changes);
        id = updated.id;
      } else {
        const created = await createMobileSupplierDevice({
          name: form.name,
          gpu_model: form.gpu_model,
          memory: form.memory,
          price: Number(form.price),
          stock: Number(form.stock),
          region_code: form.region_code,
          region_name: form.region_name,
          city: form.city,
          desc: form.desc || "供应商通过 Web 上架",
        });
        id = created.id;
      }
      setEditing(false);
      await load(id);
    } catch (reason) {
      if (!(selected && await refreshAfterConflict(reason, selected.id))) setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(item: MobileSupplierDevice) {
    try {
      await updateMobileSupplierDevice(item.id, item.version, {
        status: item.list_status === "on" ? "off" : "on",
      });
      await load(item.id);
    } catch (reason) {
      if (!(await refreshAfterConflict(reason, item.id))) setError(errorMessage(reason));
    }
  }

  async function remove(item: MobileSupplierDevice) {
    if (!window.confirm(`确定删除“${item.name}”吗？`)) return;
    try {
      await deleteMobileSupplierDevice(item.id, item.version);
      await load();
    } catch (reason) {
      if (!(await refreshAfterConflict(reason, item.id))) setError(errorMessage(reason));
    }
  }

  async function refreshAfterConflict(reason: unknown, preferredId?: number) {
    if (!(reason instanceof ApiError) || reason.status !== 409) return false;
    setEditing(false);
    await load(preferredId);
    setError("商品信息已发生变化，请确认最新库存后重新编辑");
    return true;
  }

  return (
    <section className="workspace-page commerce-workspace resource-workspace">
      <div className="workspace-page__head resource-head">
        <div>
          <p>SUPPLIER / PRODUCTS</p>
          <h1>算力商品</h1>
          <span>统一管理商品、库存、价格和上下架状态；资源参数与可售库存由商家自行申报。</span>
        </div>
        <button className="commerce-primary" onClick={startCreate}>
          <Plus size={16} />
          新增商品
        </button>
      </div>
      {error && <div className="commerce-error">{error}</div>}
      <div className="resource-console">
        <aside>
          <header>
            <strong>算力商品</strong>
            <small>{rows.length} 条</small>
          </header>
          {rows.length ? (
            rows.map((item) => (
              <button
                type="button"
                className={selected?.id === item.id && !editing ? "active" : ""}
                key={item.id}
                onClick={() => {
                  setSelected(item);
                  setEditing(false);
                }}
              >
                <span>
                  <small>{displayBusinessReference(`WOD-P-${item.id}`)}</small>
                  <strong>{item.name}</strong>
                  <em>
                    {item.gpu_model} · {item.region}
                  </em>
                </span>
                <span>
                  <b className={`status-chip status-chip--${item.list_status === "on" ? "published" : "archived"}`}>{item.list_status === "on" ? "已上架" : "已下架"}</b>
                  <i>库存 {item.stock}</i>
                </span>
              </button>
            ))
          ) : (
            <div className="commerce-empty">
              <Cube size={22} />
              <strong>还没有商品</strong>
              <span>新增后会保存到统一业务平台。</span>
            </div>
          )}
        </aside>
        <main>
          {editing ? (
            <form className="resource-form" onSubmit={(event) => void save(event)}>
              <header>
                <p>{selected ? `EDIT / ${displayBusinessReference(`WOD-P-${selected.id}`)}` : "NEW MOBILE PRODUCT"}</p>
                <h2>{selected ? "编辑商品" : "新增算力商品"}</h2>
              </header>
              <div className="resource-form__grid">
                <label>
                  <span>商品名称</span>
                  <input required minLength={2} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
                </label>
                <label>
                  <span>GPU 型号</span>
                  <input required disabled={Boolean(selected)} value={form.gpu_model} onChange={(event) => setForm({ ...form, gpu_model: event.target.value })} />
                </label>
                <label>
                  <span>显存</span>
                  <input required disabled={Boolean(selected)} value={form.memory} onChange={(event) => setForm({ ...form, memory: event.target.value })} />
                </label>
                <label>
                  <span>每 GPU 小时价格（卡时）</span>
                  <input required type="number" min="0.0001" step="0.0001" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} />
                </label>
                <label>
                  <span>库存</span>
                  <input required type="number" min="0" value={form.stock} onChange={(event) => setForm({ ...form, stock: event.target.value })} />
                </label>
                <label>
                  <span>区域代码</span>
                  <input required disabled={Boolean(selected)} value={form.region_code} onChange={(event) => setForm({ ...form, region_code: event.target.value })} />
                </label>
                <label>
                  <span>区域名称</span>
                  <input required disabled={Boolean(selected)} value={form.region_name} onChange={(event) => setForm({ ...form, region_name: event.target.value })} />
                </label>
                <label>
                  <span>城市</span>
                  <input required disabled={Boolean(selected)} value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} />
                </label>
                {!selected && (
                  <label className="resource-form__wide">
                    <span>商品说明</span>
                    <textarea value={form.desc} onChange={(event) => setForm({ ...form, desc: event.target.value })} />
                  </label>
                )}
              </div>
              <footer>
                <button type="button" onClick={() => setEditing(false)}>
                  取消
                </button>
                <button className="commerce-primary" disabled={busy}>
                  <FloppyDisk size={16} />
                  {busy ? "保存中…" : "保存商品"}
                </button>
              </footer>
            </form>
          ) : selected ? (
            <div className="resource-dossier">
              <header>
                <div>
                  <p>{displayBusinessReference(`WOD-P-${selected.id}`)}</p>
                  <h2>{selected.name}</h2>
                  <span>
                    {selected.gpu_model} · {selected.memory}
                  </span>
                </div>
                <b className={`status-chip status-chip--${selected.list_status === "on" ? "published" : "archived"}`}>{selected.list_status === "on" ? "已上架" : "已下架"}</b>
              </header>
              <div className="order-facts">
                <div>
                  <small>每小时价格</small>
                  <strong>{selected.price.toFixed(4)} 卡时 / GPU·小时</strong>
                </div>
                <div>
                  <small>当前库存</small>
                  <strong>{selected.stock}</strong>
                </div>
                <div>
                  <small>累计订单</small>
                  <strong>{selected.order_count}</strong>
                </div>
              </div>
              <footer className="order-actions">
                <button className="commerce-primary" onClick={() => startEdit(selected)}>
                  编辑价格与库存
                </button>
                <button onClick={() => void toggle(selected)}>{selected.list_status === "on" ? "下架" : "上架"}</button>
                <button className="commerce-danger" onClick={() => void remove(selected)}>
                  <Trash size={16} />
                  删除
                </button>
              </footer>
            </div>
          ) : (
            <div className="commerce-empty">
              <Cube size={28} />
              <strong>选择一个商品或新增商品</strong>
            </div>
          )}
        </main>
      </div>
    </section>
  );
}
