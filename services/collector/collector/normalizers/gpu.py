import re


_EXACT_ALIASES = {
    "MTT S4000": "MTTS4000",
    "MTTS4000": "MTTS4000",
    "TESLA T4": "T4",
    "TESLA V100": "V100",
    "RTX PRO 6000 WS": "RTXPRO6000",
    "RTX PRO 6000": "RTXPRO6000",
    "RTXPRO6000": "RTXPRO6000",
    "V-48G": "VGPU48",
    "V-32G": "VGPU32",
}


def canonicalize_gpu(name: str | None) -> str | None:
    if not name:
        return None
    raw = re.sub(r"\s+", " ", name.replace("_", " ").strip()).upper()
    raw = raw.replace("NVIDIA ", "").replace("GEFORCE ", "")
    if raw in _EXACT_ALIASES:
        return _EXACT_ALIASES[raw]
    models = (
        "B300", "B200", "H200", "H100", "H800", "H20", "A100", "A800", "A6000",
        "A5000", "A4000", "A40", "A30", "A10", "L40S", "L40", "V100", "T4",
    )
    for model in models:
        if re.search(rf"(^|[^A-Z0-9]){re.escape(model)}([^A-Z0-9]|$)", raw):
            return model
    match = re.search(r"RTX\s*(?:PRO\s*)?(\d{4})(?:\s*(TI|SUPER|D))?", raw)
    if match:
        suffix = match.group(2) or ""
        if "PRO" in raw and match.group(1) == "6000":
            return "RTXPRO6000"
        return f"RTX{match.group(1)}{suffix}"
    match = re.search(r"VGPU\s*[- ]?\s*(\d+)", raw)
    return f"VGPU{match.group(1)}" if match else None


def normalize_gpu_variant(model: str, memory_mb: int | None) -> str:
    if not memory_mb or memory_mb <= 0:
        return ""
    variant = f"{int(round(memory_mb / 1024))}GB"
    if model == "H200" and variant in {"140GB", "141GB"}:
        return "141GB"
    return variant
