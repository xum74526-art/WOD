"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from "react";
import {
  CheckCircle,
  Cube,
  FloppyDisk,
  PaperPlaneTilt,
  Plus,
  Trash,
  XCircle,
} from "@phosphor-icons/react";
import {
  createSupplierResource,
  deleteSupplierResource,
  getSupplierResource,
  listInventoryReservations,
  listSupplierResources,
  releaseInventoryReservation,
  transitionSupplierResource,
  updateSupplierResource,
  type InventoryReservation,
  type Resource,
  type ResourceDetail,
} from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney } from "@/lib/commerce-ui";

const statusLabel = {
  draft: "草稿",
  pending_review: "待审核",
  approved: "审核通过",
  published: "已发布",
  rejected: "已驳回",
  archived: "已归档",
} as const;
const reservationLabel = {
  reserved: "已预留",
  allocated: "交付占用",
  released: "已释放",
} as const;
const blank = {
  name: "",
  gpu_model: "NVIDIA H100",
  gpu_memory_gb: "80",
  region: "CN-East",
  cpu_cores: "",
  ram_gb: "",
  disk_gb: "",
  bandwidth_mbps: "",
  description: "",
  price_amount: "",
  public_host: "127.0.0.1",
  ssh_port: "22",
  ssh_username: "kai",
  agent_mode: "mtls",
};

function CapacityRail({ row }: { row: Resource }) {
  const occupied = row.total_quantity
    ? Math.min(100, (row.reserved_quantity / row.total_quantity) * 100)
    : 0;
  return (
    <div
      className="capacity-block"
      aria-label={`独占服务器状态：已占用 ${row.reserved_quantity ? "是" : "否"}`}
    >
      <div className="capacity-block__numbers">
        <span>
          <small>交付方式</small>
          <strong>整机独占</strong>
        </span>
        <span>
          <small>租用状态</small>
          <strong>{row.reserved_quantity ? "已租" : "空闲"}</strong>
        </span>
        <span>
          <small>可购买</small>
          <strong>{row.available_quantity ? "是" : "否"}</strong>
        </span>
      </div>
      <div className="capacity-rail">
        <i style={{ "--occupied": `${occupied}%` } as CSSProperties} />
      </div>
    </div>
  );
}

export function ResourceWorkspace() {
  const [rows, setRows] = useState<Resource[]>([]);
  const [detail, setDetail] = useState<ResourceDetail | null>(null);
  const [reservations, setReservations] = useState<InventoryReservation[]>([]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(
    async (preferredId?: number) => {
      setError("");
      try {
        const [resources, inventory] = await Promise.all([
          listSupplierResources(),
          listInventoryReservations(),
        ]);
        setRows(resources.data);
        setReservations(inventory.data);
        const id = preferredId ?? detail?.resource.id ?? resources.data[0]?.id;
        if (id && resources.data.some((row) => row.id === id))
          setDetail(await getSupplierResource(id));
        else setDetail(null);
      } catch (reason) {
        setError(errorMessage(reason));
      }
    },
    [detail?.resource.id],
  );
  useEffect(() => {
    void load();
  }, []);
  function edit(row: Resource) {
    setCreating(false);
    setEditing(true);
    setForm({
      name: row.name,
      gpu_model: row.gpu_model,
      gpu_memory_gb: String(row.gpu_memory_gb),
      region: row.region,
      cpu_cores: row.cpu_cores ? String(row.cpu_cores) : "",
      ram_gb: row.ram_gb ? String(row.ram_gb) : "",
      disk_gb: row.disk_gb ? String(row.disk_gb) : "",
      bandwidth_mbps: row.bandwidth_mbps ? String(row.bandwidth_mbps) : "",
      description: row.description,
      price_amount: row.price.amount,
      public_host: row.server?.public_host || "127.0.0.1",
      ssh_port: String(row.server?.ssh_port || 22),
      ssh_username: row.server?.ssh_username || "kai",
      agent_mode: row.server?.agent_mode || "mtls",
    });
  }
  function payload() {
    const optional = (value: string) => (value ? Number(value) : null);
    return {
      name: form.name,
      gpu_model: form.gpu_model,
      gpu_memory_gb: Number(form.gpu_memory_gb),
      region: form.region,
      cpu_cores: optional(form.cpu_cores),
      ram_gb: optional(form.ram_gb),
      disk_gb: optional(form.disk_gb),
      bandwidth_mbps: optional(form.bandwidth_mbps),
      description: form.description,
      price_amount: form.price_amount,
      price_currency: "CNY",
      price_unit: "server_hour",
      total_quantity: 1,
      public_host: form.public_host,
      ssh_port: Number(form.ssh_port),
      ssh_username: form.ssh_username,
      agent_mode: form.agent_mode,
    };
  }
  async function run(
    name: string,
    action: () => Promise<unknown>,
    preferredId?: number,
  ) {
    setBusy(name);
    setError("");
    try {
      await action();
      setCreating(false);
      setEditing(false);
      await load(preferredId);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy("");
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (editing && detail)
      await run(
        "save",
        () =>
          updateSupplierResource(detail.resource.id, {
            ...payload(),
            version: detail.resource.version,
            change_note: "商家工作台更新",
          }),
        detail.resource.id,
      );
    else
      await run("save", async () => {
        const created = await createSupplierResource(payload());
        await load(created.id);
      });
  }
  async function select(id: number) {
    setCreating(false);
    setEditing(false);
    setError("");
    try {
      setDetail(await getSupplierResource(id));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }
  const row = detail?.resource;
  return (
    <section className="workspace-page commerce-workspace resource-workspace">
      <div className="workspace-page__head resource-head">
        <div>
          <p>SUPPLIER / SERVER LISTINGS</p>
          <h1>服务器商品</h1>
          <span>
            登记服务器规格、SSH 入口与 Agent；审核通过后买家可按小时租用。
          </span>
        </div>
        <button
          className="commerce-primary"
          onClick={() => {
            setCreating(true);
            setEditing(false);
            setForm(blank);
          }}
        >
          <Plus size={16} />
          登记服务器
        </button>
      </div>
      {error && <div className="commerce-error">{error}</div>}
      <div className="resource-console">
        <aside>
          <header>
            <strong>资源台账</strong>
            <small>{rows.length} 条</small>
          </header>
          {rows.length ? (
            rows.map((item) => (
              <button
                type="button"
                className={row?.id === item.id && !creating ? "active" : ""}
                key={item.id}
                onClick={() => void select(item.id)}
              >
                <span>
                  <small>{item.resource_no}</small>
                  <strong>{item.name}</strong>
                  <em>
                    {item.gpu_model} · {item.region}
                  </em>
                </span>
                <span>
                  <b className={`status-chip status-chip--${item.status}`}>
                    {statusLabel[item.status]}
                  </b>
                  <i>
                    {item.available_quantity ? "当前可租" : "租用中"}
                  </i>
                </span>
              </button>
            ))
          ) : (
            <div className="commerce-empty">
              <Cube size={22} />
              <strong>还没有资源</strong>
            </div>
          )}
        </aside>
        <main>
          {creating || editing ? (
            <form
              className="resource-form"
              onSubmit={(event) => void save(event)}
            >
              <header>
                <p>{editing ? `EDIT / ${row?.resource_no}` : "NEW SERVER"}</p>
                <h2>{editing ? "编辑服务器草稿" : "登记一台服务器"}</h2>
              </header>
              <div className="resource-form__grid">
                <label>
                  <span>商品名称</span>
                  <input
                    required
                    minLength={3}
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </label>
                <label>
                  <span>GPU 型号</span>
                  <input
                    required
                    value={form.gpu_model}
                    onChange={(e) =>
                      setForm({ ...form, gpu_model: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>显存（GB）</span>
                  <input
                    required
                    type="number"
                    min="1"
                    value={form.gpu_memory_gb}
                    onChange={(e) =>
                      setForm({ ...form, gpu_memory_gb: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>区域</span>
                  <input
                    required
                    value={form.region}
                    onChange={(e) =>
                      setForm({ ...form, region: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>公网 IP 或域名</span>
                  <input
                    required
                    value={form.public_host}
                    onChange={(e) =>
                      setForm({ ...form, public_host: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>SSH 端口</span>
                  <input
                    required
                    type="number"
                    min="1"
                    max="65535"
                    value={form.ssh_port}
                    onChange={(e) =>
                      setForm({ ...form, ssh_port: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>租户账号前缀</span>
                  <input
                    required
                    value={form.ssh_username}
                    onChange={(e) =>
                      setForm({ ...form, ssh_username: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>Agent 模式</span>
                  <select
                    value={form.agent_mode}
                    onChange={(e) =>
                      setForm({ ...form, agent_mode: e.target.value })
                    }
                  >
                    <option value="mtls">KAI Agent（Linux / Windows / Docker）</option>
                    <option value="local_simulator">本机模拟器（仅界面测试）</option>
                  </select>
                </label>
                <label>
                  <span>CPU 核数</span>
                  <input
                    type="number"
                    min="1"
                    value={form.cpu_cores}
                    onChange={(e) =>
                      setForm({ ...form, cpu_cores: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>内存（GB）</span>
                  <input
                    type="number"
                    min="1"
                    value={form.ram_gb}
                    onChange={(e) =>
                      setForm({ ...form, ram_gb: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>磁盘（GB）</span>
                  <input
                    type="number"
                    min="1"
                    value={form.disk_gb}
                    onChange={(e) =>
                      setForm({ ...form, disk_gb: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>带宽（Mbps）</span>
                  <input
                    type="number"
                    min="1"
                    value={form.bandwidth_mbps}
                    onChange={(e) =>
                      setForm({ ...form, bandwidth_mbps: e.target.value })
                    }
                  />
                </label>
                <label>
                  <span>整台服务器每小时价格（CNY）</span>
                  <input
                    required
                    type="number"
                    min="0.000001"
                    step="0.000001"
                    value={form.price_amount}
                    onChange={(e) =>
                      setForm({ ...form, price_amount: e.target.value })
                    }
                  />
                </label>
                <div className="resource-fixed-field"><span>出租单位</span><strong>1 台独占服务器</strong><small>一条商品只能绑定并出租这一台服务器。</small></div>
                <label className="resource-form__wide">
                  <span>服务器与使用说明</span>
                  <textarea
                    rows={5}
                    value={form.description}
                    onChange={(e) =>
                      setForm({ ...form, description: e.target.value })
                    }
                  />
                </label>
              </div>
              <footer>
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setEditing(false);
                  }}
                >
                  取消
                </button>
                <button className="commerce-primary" disabled={Boolean(busy)}>
                  <FloppyDisk size={15} />
                  {busy === "save" ? "保存中…" : "保存服务器草稿"}
                </button>
              </footer>
            </form>
          ) : row ? (
            <article className="resource-dossier">
              <header>
                <div>
                  <p>
                    {row.resource_no} / V{row.version}
                  </p>
                  <h2>{row.name}</h2>
                  <span>
                    {row.gpu_model} · {row.gpu_memory_gb} GB · {row.region}
                  </span>
                </div>
                <b className={`status-chip status-chip--${row.status}`}>
                  {statusLabel[row.status]}
                </b>
              </header>
              <CapacityRail row={row} />
              <dl>
                <div>
                  <dt>每小时价格</dt>
                  <dd>
                    {formatMoney(
                      row.price.amount,
                      row.price.currency,
                      row.price.unit,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>计算规格</dt>
                  <dd>
                    {row.cpu_cores || "—"} CPU · {row.ram_gb || "—"} GB RAM
                  </dd>
                </div>
                <div>
                  <dt>SSH 入口</dt>
                  <dd>
                    {row.server
                      ? `${row.server.public_host}:${row.server.ssh_port}`
                      : "未登记"}
                  </dd>
                </div>
                <div>
                  <dt>Agent</dt>
                  <dd>
                    {row.server
                      ? `${row.server.status} · ${row.server.agent_mode}`
                      : "未接入"}
                  </dd>
                </div>
              </dl>
              <section>
                <h3>服务器说明</h3>
                <p>{row.description || "暂无说明。"}</p>
              </section>
              {row.review_note && (
                <section className="resource-review-note">
                  <h3>审核意见</h3>
                  <p>{row.review_note}</p>
                </section>
              )}
              <footer>
                {["draft", "rejected", "approved"].includes(row.status) && (
                  <button onClick={() => edit(row)}>
                    <FloppyDisk size={15} />
                    编辑
                  </button>
                )}
                {["draft", "rejected"].includes(row.status) && (
                  <button
                    className="commerce-primary"
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void run(
                        "submit",
                        () =>
                          transitionSupplierResource(
                            row.id,
                            "submit-review",
                            row.version,
                          ),
                        row.id,
                      )
                    }
                  >
                    <PaperPlaneTilt size={15} />
                    提交审核
                  </button>
                )}
                {row.status === "pending_review" && (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void run(
                        "withdraw",
                        () =>
                          transitionSupplierResource(
                            row.id,
                            "withdraw-review",
                            row.version,
                          ),
                        row.id,
                      )
                    }
                  >
                    <XCircle size={15} />
                    撤回审核
                  </button>
                )}
                {row.status === "approved" && (
                  <button
                    className="commerce-primary"
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void run(
                        "publish",
                        () =>
                          transitionSupplierResource(
                            row.id,
                            "publish",
                            row.version,
                          ),
                        row.id,
                      )
                    }
                  >
                    <CheckCircle size={15} />
                    发布服务器
                  </button>
                )}
                {row.status === "published" && (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void run(
                        "unpublish",
                        () =>
                          transitionSupplierResource(
                            row.id,
                            "unpublish",
                            row.version,
                          ),
                        row.id,
                      )
                    }
                  >
                    下架服务器
                  </button>
                )}
                {["draft", "rejected"].includes(row.status) && (
                  <button
                    className="commerce-danger"
                    disabled={Boolean(busy)}
                    onClick={() => {
                      if (window.confirm("确认删除这台服务器草稿？"))
                        void run("delete", () =>
                          deleteSupplierResource(row.id, row.version),
                        );
                    }}
                  >
                    <Trash size={15} />
                    删除
                  </button>
                )}
              </footer>
              {detail && (
                <section className="price-history">
                  <h3>价格版本</h3>
                  {detail.price_versions.map((version) => (
                    <div key={version.id}>
                      <span>
                        V{version.version} · {formatDate(version.created_at)}
                      </span>
                      <strong>
                        {formatMoney(
                          version.amount,
                          version.currency,
                          version.unit,
                        )}
                      </strong>
                      <small>{version.change_note || "价格记录"}</small>
                    </div>
                  ))}
                </section>
              )}
            </article>
          ) : (
            <div className="commerce-empty">
              <Cube size={26} />
              <strong>选择或登记一台服务器</strong>
            </div>
          )}
        </main>
      </div>
      <section className="inventory-ledger">
        <header>
          <div>
            <p>INVENTORY LEDGER</p>
            <h2>容量占用流水</h2>
          </div>
          <span>预留与交付占用都会计入可用容量；订单完成后由商家释放。</span>
        </header>
        {reservations.length ? (
          <div className="inventory-table">
            {reservations.map((item) => (
              <article key={item.id}>
                <div>
                  <small>{item.reservation_no}</small>
                  <strong>{item.resource_name}</strong>
                  <span>{item.order_no}</span>
                </div>
                <b>{item.quantity}</b>
                <span className={`status-chip status-chip--${item.status}`}>
                  {reservationLabel[item.status]}
                </span>
                {item.status !== "released" && (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() => {
                      const reason = window.prompt(
                        "请输入释放原因",
                        "订单已完成，释放占用容量",
                      );
                      if (reason)
                        void run("release", () =>
                          releaseInventoryReservation(
                            item.id,
                            item.version,
                            reason,
                          ),
                        );
                    }}
                  >
                    释放容量
                  </button>
                )}
              </article>
            ))}
          </div>
        ) : (
          <div className="commerce-empty">
            <Cube size={21} />
            <strong>当前没有容量占用记录</strong>
          </div>
        )}
      </section>
    </section>
  );
}
