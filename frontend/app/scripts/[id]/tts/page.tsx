"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

export default function TtsPage() {
  const params = useParams<{ id: string }>();
  const jobId = typeof params?.id === "string" ? params.id : "";
  const { push } = useToast();
  const [result, setResult] = useState<unknown>(null);
  const sectionType = "hook";
  const voice = "P";
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runTts = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.generateTts(jobId, { section_type: sectionType, voice });
      setResult(res);
    } catch (err) {
      const message = err instanceof Error ? err.message : "TTS failed.";
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
        const res = await api.generateTts(jobId, { section_type: sectionType, voice });
        if (!cancelled) setResult(res);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "TTS failed.";
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
  }, [jobId, sectionType, voice, push]);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Text to Speech</h1>
      <p className="text-muted-foreground">Generate TTS audio for a script section.</p>
      {error ? <div className="card border-red-500/50">{error}</div> : null}
      {loading ? <p className="text-muted-foreground">Generating TTS…</p> : null}
      {!loading && result ? <pre className="card overflow-auto text-xs">{JSON.stringify(result, null, 2)}</pre> : null}
      <button type="button" className="btn-secondary" disabled={loading} onClick={() => void runTts()}>
        {loading ? "Generating…" : "Generate TTS"}
      </button>
    </div>
  );
}
