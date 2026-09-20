"use client";

import { useEffect, useState } from "react";
import { fallbackWebProductImage, resolveWebProductImage } from "@/lib/product-image";

export function ProductImage({
  imageUrl,
  gpuModel,
  className,
  eager = false,
}: {
  imageUrl?: string | null;
  gpuModel?: string | null;
  className?: string;
  eager?: boolean;
}) {
  const resolved = resolveWebProductImage(imageUrl, gpuModel);
  const fallback = fallbackWebProductImage(gpuModel);
  const [source, setSource] = useState(resolved);

  useEffect(() => setSource(resolved), [resolved]);

  return <img
    className={className}
    src={source}
    alt={`${gpuModel || "GPU"} 算力资源`}
    loading={eager ? "eager" : "lazy"}
    decoding="async"
    referrerPolicy="no-referrer"
    onError={() => { if (source !== fallback) setSource(fallback); }}
  />;
}
