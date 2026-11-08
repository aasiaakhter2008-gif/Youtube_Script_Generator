"use client";

import { useState, type FormEvent } from "react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import type { SeriesPlan } from "@/lib/types";

export default function PlansPage() {
  const { push } = useToast();
  const [niche, setNiche] = useState("technology");
  const [goal, setGoal] = useState("");
  const [episodes, setEpisodes] = useState("4");
  const [plan, setPlan] = useState<SeriesPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createPlan = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.createPlan({ niche, goal: goal.trim() || undefined, episodes: Number(episodes) || 4 });
      setPlan(res);
      push("Series plan created.", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create plan.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold tracking-tight">Content Plans</h1>

      <form className="card space-y-4" onSubmit={createPlan}>
        <h2 className="font-semibold">Create series plan</h2>
        <div>
          <label className="label" htmlFor="niche">Niche</label>
          <input id="niche" className="input" value={niche} onChange={(e) => setNiche(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="goal">Goal</label>
          <input id="goal" className="input" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. grow audience around AI tools" />
        </div>
        <div>
          <label className="label" htmlFor="episodes">Episodes</label>
          <input id="episodes" className="input" type="number" min={1} max={12} value={episodes} onChange={(e) => setEpisodes(e.target.value)} />
        </div>
        <button type="submit" className="btn-primary" disabled={loading || !niche.trim()}>
          {loading ? "Creating…" : "Create Plan"}
        </button>
      </form>

      {error ? <div className="card border-red-500/50">{error}</div> : null}

      {plan ? (
        <div className="card space-y-4">
          <h2 className="font-semibold">Plan {plan.id}</h2>
          <p className="text-sm">Series: {plan.series_title}</p>
          <div className="space-y-2">
            {(plan.episodes ?? []).map((ep) => (
              <div key={ep.id} className="rounded border border-border p-3">
                <p className="font-medium">{ep.title}</p>
                <p className="text-sm text-muted-foreground">{ep.angle}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
