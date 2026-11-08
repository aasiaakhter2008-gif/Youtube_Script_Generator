"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import type { ScriptSummary } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  pending: "border-yellow-500/40 bg-yellow-950/40 text-yellow-300",
  running: "border-blue-500/40 bg-blue-950/40 text-blue-300",
  completed: "border-green-500/40 bg-green-950/40 text-green-300",
  failed: "border-red-500/40 bg-red-950/40 text-red-300",
  draft: "border-border bg-muted text-muted-foreground",
  review: "border-purple-500/40 bg-purple-950/40 text-purple-300",
  approved: "border-teal-500/40 bg-teal-950/40 text-teal-300",
  published: "border-pink-500/40 bg-pink-950/40 text-pink-300",
};

export default function HistoryPage() {
  const router = useRouter();
  const { push } = useToast();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listScripts();
      setScripts(Array.isArray(data) ? data : []);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load scripts.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = scripts.filter((s) => s.topic.toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Script History</h1>
          <p className="mt-2 text-muted-foreground">Previously generated YouTube scripts.</p>
        </div>
        <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <div>
        <input
          className="input"
          placeholder="Search by topic…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search scripts by topic"
        />
      </div>

      {error ? <div className="card border-red-500/50">{error}</div> : null}

      {!error && filtered.length === 0 ? (
        <div className="card text-center text-muted-foreground">No scripts found.</div>
      ) : null}

      <div className="space-y-3">
        {filtered.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => router.push(`/scripts/${s.id}`)}
            className="card w-full text-left transition-colors hover:border-foreground/40"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold">{s.topic}</span>
              <span className={`rounded-full border px-3 py-1 text-xs uppercase tracking-wide ${STATUS_STYLES[s.status] ?? "border-border bg-muted text-foreground"}`}>
                {s.status}
              </span>
            </div>
            <div className="mt-2 text-sm text-muted-foreground">
              {s.duration_minutes} min · {s.format ?? "long_form"} · {new Date(s.created_at).toLocaleString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
