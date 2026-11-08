"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

export default function HookTestsPage() {
  const params = useParams<{ id: string }>();
  const jobId = typeof params?.id === "string" ? params.id : "";
  const { push } = useToast();
  const [plan, setPlan] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.createHookTests(jobId);
        if (!cancelled) setPlan(res);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to create hook tests.";
        setError(message);
        push(message, "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [jobId, push]);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Hook Tests</h1>
      <p className="text-muted-foreground">AI hook variant generation and evaluation for this script.</p>
      {error ? <div className="card border-red-500/50">{error}</div> : null}
      {loading ? <p className="text-muted-foreground">Generating hook tests…</p> : null}
      {!loading && plan ? <pre className="card overflow-auto text-xs">{JSON.stringify(plan, null, 2)}</pre> : null}
    </div>
  );
}
