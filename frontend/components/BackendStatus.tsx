"use client";

import { useEffect, useState } from "react";
import { checkBackendHealth } from "@/lib/api";

/**
 * Free-tier hosts (Render/Railway/HF) spin down when idle. This banner polls /health
 * and tells the user the server is waking instead of letting requests look broken.
 */
export function BackendStatus() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const loop = async () => {
      const ok = await checkBackendHealth();
      if (cancelled) return;
      setOnline(ok);
      // Fast retry while waking; gentle check when healthy.
      timer = setTimeout(loop, ok ? 30000 : 5000);
    };

    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (online) return null;

  return (
    <div className="border-b border-amber-500/40 bg-amber-950/40 px-4 py-2 text-center text-sm text-amber-200">
      Waking up the free server — this can take up to ~60 seconds. Retrying automatically…
    </div>
  );
}
