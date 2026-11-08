"use client";

import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

export default function BillingPage() {
  const { push } = useToast();
  const [plans, setPlans] = useState<unknown[]>([]);
  const [usage, setUsage] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await api.listBillingPlans();
      const u = await api.getBillingUsage();
      setPlans(Array.isArray(p) ? p : []);
      setUsage(u);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load billing info.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const subscribe = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.subscribe("pro", "user-1");
      void res;
      push("Subscribed to Pro plan.", "success");
      const u = await api.getBillingUsage();
      setUsage(u);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Subscription failed.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold tracking-tight">Billing</h1>

      {error ? <div className="card border-red-500/50">{error}</div> : null}

      <div className="card space-y-3">
        <h2 className="font-semibold">Plans</h2>
        {loading ? <p className="text-muted-foreground">Loading plans…</p> : null}
        {!loading && plans.length === 0 ? <p className="text-muted-foreground">No plans available.</p> : null}
        {plans.map((p, i) => (
          <pre key={i} className="overflow-auto rounded border border-border p-3 text-xs">{JSON.stringify(p, null, 2)}</pre>
        ))}
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold">Usage</h2>
        <pre className="overflow-auto rounded border border-border p-3 text-xs">{JSON.stringify(usage, null, 2)}</pre>
        <button type="button" className="btn-primary" onClick={() => void subscribe()} disabled={loading}>
          Subscribe to Pro
        </button>
      </div>
    </div>
  );
}
