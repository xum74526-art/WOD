import { CheckCircle, ClockCountdown } from "@phosphor-icons/react/dist/ssr";
import type { WorkspaceFeature } from "@/lib/workspace-features";

export function WorkspaceFeaturePage({ feature }: { feature: WorkspaceFeature }) {
  return (
    <section className="workspace-page">
      <div className="workspace-page__head"><p>北斗 kai WORKSPACE</p><h1>{feature.title}</h1><span>{feature.description}</span></div>
      <div className="workspace-state"><ClockCountdown size={25} /><div><strong>{feature.status}</strong><span>页面不会使用演示数据冒充真实业务记录。</span></div></div>
      <div className="workspace-columns">
        <section><h2>已准备</h2><ul>{feature.available.map((item) => <li key={item}><CheckCircle size={17} />{item}</li>)}</ul></section>
        <section><h2>启用前需要</h2><ul>{feature.pending.map((item) => <li key={item}><ClockCountdown size={17} />{item}</li>)}</ul></section>
      </div>
    </section>
  );
}
