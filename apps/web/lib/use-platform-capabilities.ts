"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FAIL_CLOSED_PLATFORM_CAPABILITIES,
  getPlatformCapabilities,
  type PlatformCapabilities,
} from "@/lib/platform-capabilities";

export function usePlatformCapabilities() {
  const [capabilities, setCapabilities] = useState<PlatformCapabilities>(FAIL_CLOSED_PLATFORM_CAPABILITIES);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setCapabilities(await getPlatformCapabilities());
    } catch {
      setCapabilities(FAIL_CLOSED_PLATFORM_CAPABILITIES);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { capabilities, loading, refresh };
}
