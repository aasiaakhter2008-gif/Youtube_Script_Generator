"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api, getApiKey, streamScriptEvents } from "@/lib/api";
import type { DailyQuota, PipelineEvent, ScriptJobRead, ScriptStatus, WrittenScript } from "@/lib/types";

const TONES = ["educational", "funny", "storytelling", "motivational"] as const;
const LANGUAGES = ["English", "Urdu", "Roman Urdu", "Hindi"] as const;
const FORMATS = ["long_form", "shorts"] as const;

export default function NewScriptPage() {
  const router = useRouter();
  const { push } = useToast();

  const [apiKeyReady, setApiKeyReady] = useState(false);
  const [topic, setTopic] = useState("");
  const [audience, setAudience] = useState("");
  const [tone, setTone] = useState<string>("educational");
  const [language, setLanguage] = useState<string>("English");
  const [durationMinutes, setDurationMinutes] = useState("8");
  const [format, setFormat] = useState<string>("long_form");
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [job, setJob] = useState<ScriptJobRead | null>(null);
  const [finalScript, setFinalScript] = useState<WrittenScript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<DailyQuota | null>(null);

  const refreshQuota = useCallback(async () => {
    try {
      setQuota(await api.getQuota());
    } catch {
      // Quota is a convenience indicator; never block generation on it.
    }
  }, []);

  useEffect(() => {
    setApiKeyReady(Boolean(getApiKey()));
    if (getApiKey()) void refreshQuota();
  }, [refreshQuota]);

  const handleEvent = useCallback((event: PipelineEvent) => {
    setEvents((prev) => [...prev, event]);
    if (event.event === "failed") {
      setError(event.error ?? "Script generation failed.");
    }
  }, []);

  const streamJob = useCallback(
    async (id: string) => {
      await streamScriptEvents(id, handleEvent);
    },
    [handleEvent],
  );

  const finalizeAfterJob = useCallback(async (id: string) => {
    try {
      const updated = await api.getScript(id);
      setJob(updated);
      if (updated.status === "completed" && updated.final_script) {
        setFinalScript(updated.final_script);
      } else if (updated.status === "failed") {
        setError(updated.error ?? "Script generation failed.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load script status.";
      setError(message);
    }
  }, []);

  const runGeneration = useCallback(
    async (topicValue: string) => {
      setLoading(true);
      setError(null);
      setEvents([]);
      setFinalScript(null);
      setJob(null);
      try {
        const accepted = await api.generateScript({
          topic: topicValue,
          audience: audience.trim() || undefined,
          tone: tone as never,
          language: language as never,
          duration_minutes: Number(durationMinutes) || 8,
          format: format as never,
        });
        const id = accepted.job_id;
        setJobId(id);
        await streamJob(id);
        await finalizeAfterJob(id);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to start script generation.";
        setError(message);
        push(message, "error");
      } finally {
        setLoading(false);
        void refreshQuota();
      }
    },
    [audience, format, language, push, tone, durationMinutes, streamJob, finalizeAfterJob, refreshQuota],
  );

  const retryJob = useCallback(async () => {
    if (!jobId || loading) return;
    setLoading(true);
    setError(null);
    setEvents([]);
    setFinalScript(null);
    try {
      await api.retryScript(jobId);
      await streamJob(jobId);
      await finalizeAfterJob(jobId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Retry failed.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
      void refreshQuota();
    }
  }, [jobId, loading, push, streamJob, finalizeAfterJob, refreshQuota]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = topic.trim();
    if (!trimmed) return;
    if (!Number.isFinite(Number(durationMinutes)) || Number(durationMinutes) < 1 || Number(durationMinutes) > 30) {
      push("Duration must be between 1 and 30 minutes.", "error");
      return;
    }
    await runGeneration(trimmed);
  };

  if (!apiKeyReady) {
    return (
      <div className="card">
        <h1 className="text-2xl font-semibold">YouTube Script Generator</h1>
        <p className="mt-2 text-muted-foreground">Add your API key to start generating scripts.</p>
        <Link href="/settings" className="btn-primary mt-4 inline-flex h-10 items-center">
          Go to Settings
        </Link>
      </div>
    );
  }

  const status: ScriptStatus | null = job?.status ?? null;
  const lastRetry = [...events].reverse().find((event) => event.event === "llm.retry") ?? null;
  const quotaExhausted = quota != null && !quota.unlimited && (quota.remaining ?? 0) <= 0;
  const resetsAt = quota ? new Date(quota.resets_at) : null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">New Script</h1>
        <p className="mt-2 text-muted-foreground">Generate a YouTube script with the multi-agent pipeline.</p>
        {quota && !quota.unlimited ? (
          <p className={`mt-3 text-sm ${quotaExhausted ? "text-red-500" : "text-muted-foreground"}`}>
            {quotaExhausted
              ? `Daily free quota exhausted. Resets ${resetsAt ? resetsAt.toLocaleString() : "soon"}.`
              : `Free quota: ${quota.remaining} of ${quota.limit} generations left today · resets ${resetsAt ? resetsAt.toLocaleTimeString() : "at midnight UTC"}.`}
          </p>
        ) : null}
      </div>

      <form className="card space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="label" htmlFor="topic">Topic *</label>
          <input id="topic" className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. The Science of Sleep" maxLength={300} required />
        </div>
        <div>
          <label className="label" htmlFor="audience">Audience</label>
          <input id="audience" className="input" value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="e.g. College students" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="tone">Tone</label>
            <select id="tone" className="input" value={tone} onChange={(e) => setTone(e.target.value)}>
              {TONES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="language">Language</label>
            <select id="language" className="input" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="duration">Duration (minutes)</label>
            <input id="duration" className="input" type="number" min={1} max={30} value={durationMinutes} onChange={(e) => setDurationMinutes(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="format">Format</label>
            <select id="format" className="input" value={format} onChange={(e) => setFormat(e.target.value)}>
              {FORMATS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
        </div>
        <button type="submit" className="btn-primary" disabled={loading || !topic.trim() || quotaExhausted}>
          {loading ? "Generating…" : quotaExhausted ? "Daily quota exhausted" : "Generate Script"}
        </button>
        {quotaExhausted ? (
          <p className="text-sm text-muted-foreground">
            Your free daily quota resets at {resetsAt ? resetsAt.toLocaleString() : "midnight UTC"}. Generation will
            work again automatically — no action needed.
          </p>
        ) : null}
      </form>

      {loading && lastRetry?.error ? (
        <div className="card flex items-center gap-3 border-amber-500/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-300">
          <span className="animate-pulse text-lg leading-none">●</span>
          <span>{lastRetry.error}</span>
        </div>
      ) : null}

      {error && (
        <div className="card border-red-500/50">
          <h2 className="font-semibold text-red-600">
            {error.toLowerCase().includes("daily generation limit") ? "Daily quota exhausted" : "Generation failed"}
          </h2>
          <p className="mt-2 whitespace-pre-wrap">{error}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            {!error.toLowerCase().includes("daily generation limit") ? (
              <button
                type="button"
                className="btn-primary"
                disabled={loading}
                onClick={() => void retryJob()}
              >
                Retry
              </button>
            ) : null}
            <button type="button" className="btn-secondary" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {jobId && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Job {jobId}</h2>
            {status && <span className="rounded-full border px-3 py-1 text-xs uppercase tracking-wide">{status}</span>}
          </div>
          {job?.model_usage && Object.keys(job.model_usage).length > 0 ? (
            <p className="text-xs text-muted-foreground">
              Models used: {Object.entries(job.model_usage).map(([role, model]) => `${role}=${model}`).join(" · ")}
            </p>
          ) : null}
          {events.length > 0 && (
            <ul className="space-y-1 text-sm">
              {events.map((event, i) =>
                event.event === "llm.retry" ? (
                  <li key={i} className="rounded border border-amber-500/30 bg-amber-950/30 px-3 py-2 text-amber-300">
                    <span className="font-mono text-xs">llm.retry</span>
                    <span className="ml-2">{event.error}</span>
                  </li>
                ) : (
                  <li key={i} className="rounded bg-muted/50 px-3 py-2">
                    <span className="font-mono text-xs">{event.event}</span>
                    {event.agent ? <span className="ml-2 text-muted-foreground">agent={event.agent}</span> : null}
                    {event.assessment?.assessment ? <span className="ml-2">critic passed={String(event.assessment.assessment.passed)}</span> : null}
                  </li>
                ),
              )}
            </ul>
          )}
          {finalScript && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">Final script · {finalScript.word_count} words</p>
              {finalScript.sections.map((section, i) => (
                <div key={i} className="rounded border border-border p-4">
                  <div className="flex items-baseline justify-between">
                    <h3 className="font-semibold">{section.title}</h3>
                    <span className="text-xs text-muted-foreground">{section.section_type}</span>
                  </div>
                  <p className="script-content mt-2 whitespace-pre-wrap">{section.content}</p>
                  {section.b_roll_cues && section.b_roll_cues.length > 0 ? (
                    <p className="mt-2 text-xs text-muted-foreground">B-roll: {section.b_roll_cues.join(", ")}</p>
                  ) : null}
                  {section.on_screen_text && section.on_screen_text.length > 0 ? (
                    <p className="mt-1 text-xs text-muted-foreground">On-screen: {section.on_screen_text.join(", ")}</p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
          {loading ? <p className="text-sm text-muted-foreground">Waiting for pipeline events…</p> : null}
        </div>
      )}

      {jobId && !loading && finalScript ? (
        <div className="flex gap-3">
          <button type="button" className="btn-secondary" onClick={() => router.push(`/scripts/${jobId}`)}>
            Open full editor
          </button>
        </div>
      ) : null}
    </div>
  );
}
