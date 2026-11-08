"use client";

import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import type { Trend } from "@/lib/types";

export default function TrendsPage() {
  const { push } = useToast();
  const [trends, setTrends] = useState<Trend[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [niche, setNiche] = useState("technology");

  const load = useCallback(async (nicheValue?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTrends(nicheValue);
      setTrends(Array.isArray(data) ? data : []);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load trends.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.refreshTrends(niche || undefined);
      const data = await api.getTrends(niche || undefined);
      setTrends(Array.isArray(data) ? data : []);
      void res;
      push("Trends refreshed.", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to refresh trends.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Trends</h1>
          <p className="mt-2 text-muted-foreground">Trending topics for script ideation.</p>
        </div>
        <button type="button" className="btn-secondary" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="flex items-end gap-3">
        <div>
          <label className="label" htmlFor="niche">Niche</label>
          <input id="niche" className="input" value={niche} onChange={(e) => setNiche(e.target.value)} />
        </div>
        <button type="button" className="btn-primary" onClick={() => void load(niche || undefined)} disabled={loading}>
          Load
        </button>
      </div>

      {error ? <div className="card border-red-500/50">{error}</div> : null}

      <div className="space-y-3">
        {trends.map((t, i) => (
          <div key={`${t.keyword}-${i}`} className="card flex items-center justify-between">
            <div>
              <span className="font-semibold">{t.keyword}</span>
              <span className="ml-2 text-sm text-muted-foreground">{t.reason}</span>
            </div>
            <span className="rounded-full border px-3 py-1 text-xs">{t.score}</span>
          </div>
        ))}
        {trends.length === 0 && !loading ? <div className="card text-center text-muted-foreground">No trends loaded.</div> : null}
      </div>
    </div>
  );
}
