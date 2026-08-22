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

    for model in ("B300", "B200", "H200", "H100", "H800", "H20", "A100", "A800", "A6000", "A5000", "A4000", "A40", "A30", "A10", "L40S", "L40", "V100", "T4"):
        if re.search(rf"(^|[^A-Z0-9]){re.escape(model)}([^A-Z0-9]|$)", raw):
            return model

    match = re.search(r"RTX\s*(?:PRO\s*)?(\d{4})(?:\s*(TI|SUPER|D))?", raw)
    if match:
        suffix = match.group(2) or ""
        if "PRO" in raw and match.group(1) == "6000":
            return "RTXPRO6000"
        return f"RTX{match.group(1)}{suffix}"

    match = re.search(r"VGPU\s*[- ]?\s*(\d+)", raw)
    if match:
        return f"VGPU{match.group(1)}"
    return None


def memory_variant_from_gb(memory_gb: float | int | None) -> str:
    if not memory_gb or memory_gb <= 0:
        return ""
    rounded = int(round(float(memory_gb)))
    return f"{rounded}GB"


def memory_variant_from_text(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*GB", value.upper())
    if not match:
        return ""
    return memory_variant_from_gb(float(match.group(1)))


def normalize_gpu_variant(model: str | None, value: str | float | int | None) -> str:
    """Normalize known provider capacity aliases without merging real SKUs.

    Most VRAM values remain exact. H200 is the one currently observed alias:
    providers publish the same board as either 140 GB (rounded binary usable
    capacity) or 141 GB (marketed capacity). Other values, including H100
    80/94 GB and RTX 5060 Ti 8/16 GB, deliberately stay separate.
    """
    if isinstance(value, str):
        variant = memory_variant_from_text(value)
    else:
        variant = memory_variant_from_gb(value)
    canonical_model = canonicalize_gpu(model) or str(model or "").strip().upper()
    if canonical_model == "H200" and variant in {"140GB", "141GB"}:
        return "141GB"
    return variant


def gpu_variant_aliases(model: str | None, value: str | float | int | None) -> set[str]:
    """Return only explicitly documented storage aliases for one exact SKU."""
    canonical_model = canonicalize_gpu(model) or str(model or "").strip().upper()
    normalized = normalize_gpu_variant(canonical_model, value)
    if canonical_model == "H200" and normalized == "141GB":
        return {"140GB", "141GB"}
    return {normalized} if normalized else set()
