type JsonObject = Record<string, unknown>;

export type MarketLatestIdentity = {
  model: string;
  variant: string | null;
};

function object(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function canonicalGpuModel(value: string) {
  let normalized = value.replaceAll("_", " ").trim().replace(/\s+/g, " ").toUpperCase();
  normalized = normalized.replaceAll("NVIDIA ", "").replaceAll("GEFORCE ", "");
  const aliases: Record<string, string> = {
    "MTT S4000": "MTTS4000",
    MTTS4000: "MTTS4000",
    "TESLA T4": "T4",
    "TESLA V100": "V100",
    "RTX PRO 6000 WS": "RTXPRO6000",
    "RTX PRO 6000": "RTXPRO6000",
    RTXPRO6000: "RTXPRO6000",
    "V-48G": "VGPU48",
    "V-32G": "VGPU32",
  };
  if (aliases[normalized]) return aliases[normalized];
  for (const model of [
    "B300", "B200", "H200", "H100", "H800", "H20", "A100", "A800", "A6000",
    "A5000", "A4000", "A40", "A30", "A10", "L40S", "L40", "V100", "T4",
  ]) {
    if (new RegExp(`(^|[^A-Z0-9])${model}([^A-Z0-9]|$)`).test(normalized)) return model;
  }
  const rtx = normalized.match(/RTX\s*(?:PRO\s*)?(\d{4})(?:\s*(TI|SUPER|D))?/);
  if (rtx) {
    if (normalized.includes("PRO") && rtx[1] === "6000") return "RTXPRO6000";
    return `RTX${rtx[1]}${rtx[2] ?? ""}`;
  }
  const vgpu = normalized.match(/VGPU\s*[- ]?\s*(\d+)/);
  return vgpu ? `VGPU${vgpu[1]}` : normalized;
}

function canonicalGpuVariant(model: string, value: string) {
  const matched = value.toUpperCase().match(/(\d+(?:\.\d+)?)\s*GB/);
  if (!matched) return "";
  const parsedMemory = Number(matched[1]);
  const lowerMemory = Math.floor(parsedMemory);
  const memory = parsedMemory - lowerMemory === 0.5
    ? lowerMemory + lowerMemory % 2
    : Math.round(parsedMemory);
  if (!Number.isFinite(memory) || memory <= 0) return "";
  if (canonicalGpuModel(model) === "H200" && (memory === 140 || memory === 141)) return "141GB";
  return `${memory}GB`;
}

function nullablePositiveNumber(value: unknown) {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value > 0);
}

export function isValidMarketLatestPayload(
  value: unknown,
  expected: MarketLatestIdentity,
): value is JsonObject {
  const data = object(value);
  if (!data) return false;
  if (typeof data.server_time !== "string" || !data.server_time.trim()) return false;
  if (typeof data.gpu_model !== "string" || !data.gpu_model.trim()) return false;
  if (typeof data.gpu_variant !== "string") return false;
  if (canonicalGpuModel(data.gpu_model) !== canonicalGpuModel(expected.model)) return false;
  if (
    expected.variant !== null
    && canonicalGpuVariant(data.gpu_model, data.gpu_variant) !== canonicalGpuVariant(expected.model, expected.variant)
  ) return false;

  const summary = object(data.summary);
  if (!summary || !("median_price_card_hours" in summary)) return false;
  if (!nullablePositiveNumber(summary.median_price_card_hours)) return false;
  if (!Number.isInteger(summary.sample_count) || Number(summary.sample_count) < 0) return false;
  if (
    typeof summary.card_hour_rmb_rate !== "number"
    || !Number.isFinite(summary.card_hour_rmb_rate)
    || summary.card_hour_rmb_rate <= 0
  ) return false;
  if (!Array.isArray(data.items)) return false;
  if (!object(data.requested_source_states)) return false;
  if (!Array.isArray(data.excluded_sources)) return false;
  return true;
}
