"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface StoryboardResponse {
  job_id: string;
  shots: {
    section_type: string;
    shot_type: string;
    visual_description: string;
    b_roll_keywords: string[];
    on_screen_text: string;
    estimated_duration_seconds: number;
  }[];
}

export default function StoryboardPage() {
  const params = useParams<{ id: string }>();
  const jobId = typeof params?.id === "string" ? params.id : "";
  const { push } = useToast();
  const [data, setData] = useState<StoryboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getStoryboard(jobId);
        if (!cancelled) setData(res as StoryboardResponse);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to load storyboard.";
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
      <h1 className="text-3xl font-bold tracking-tight">Storyboard</h1>
      {error ? <div className="card border-red-500/50">{error}</div> : null}
      {loading ? <p className="text-muted-foreground">Loading storyboard…</p> : null}
      {!loading && !error && data ? (
        <div className="card">
          <p className="text-sm text-muted-foreground">Job {data.job_id}</p>
          <div className="mt-4 space-y-3">
            {data.shots.map((shot, i) => (
              <div key={i} className="rounded border border-border p-4">
                <div className="flex items-baseline justify-between">
                  <h3 className="font-semibold">{shot.section_type}</h3>
                  <span className="text-xs text-muted-foreground">{shot.shot_type}</span>
                </div>
                <p className="mt-1 text-sm">{shot.visual_description}</p>
                <p className="mt-1 text-xs text-muted-foreground">On-screen: {shot.on_screen_text}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
