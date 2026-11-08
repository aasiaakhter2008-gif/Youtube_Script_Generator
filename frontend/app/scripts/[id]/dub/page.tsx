"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

export default function DubPage() {
  const params = useParams<{ id: string }>();
  const jobId = typeof params?.id === "string" ? params.id : "";
  const { push } = useToast();
  const [result, setResult] = useState<unknown>(null);
  const language = "Urdu";
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDub = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.dubScript(jobId, { language });
      setResult(res);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to dub script.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.dubScript(jobId, { language });
        if (!cancelled) setResult(res);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to dub script.";
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
  }, [jobId, language, push]);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Dub Script</h1>
      <p className="text-muted-foreground">Generate a dubbed version of this script.</p>
      {error ? <div className="card border-red-500/50">{error}</div> : null}
      {loading ? <p className="text-muted-foreground">Dubbing…</p> : null}
      {!loading && result ? <pre className="card overflow-auto text-xs">{JSON.stringify(result, null, 2)}</pre> : null}
      <button type="button" className="btn-secondary" disabled={loading} onClick={() => void runDub()}>
        {loading ? "Dubbing…" : "Run Dub"}
      </button>
    </div>
  );
}
