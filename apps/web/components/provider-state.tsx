import { CheckCircle, PlugsConnected, WarningCircle } from "@phosphor-icons/react";
import type { ProviderDescriptor } from "@/lib/integration-api";

const labels: Record<string, string> = {
  payment: "支付服务",
  kyc: "实名认证服务",
  object_storage: "私有对象存储",
};

export function ProviderState({ descriptor }: { descriptor: ProviderDescriptor }) {
  const configured = descriptor.configured;
  const Icon = configured ? CheckCircle : descriptor.status === "adapter_missing" ? WarningCircle : PlugsConnected;
  return (
    <div className={`provider-state ${configured ? "provider-state--ready" : ""}`}>
      <Icon size={22} />
      <div>
        <small>{labels[descriptor.kind] || descriptor.kind}</small>
        <strong>{configured ? `${descriptor.provider} 已连接` : "等待服务商配置"}</strong>
        <span>
          {descriptor.status === "adapter_missing"
            ? `已指定 ${descriptor.provider}，但适配器尚未安装`
            : configured
              ? "所有动作仍由后端权限和状态机校验"
              : "当前不会产生模拟成功记录"}
        </span>
      </div>
    </div>
  );
}
