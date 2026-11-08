"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { api, saveBlob, streamScriptEvents } from "@/lib/api";
import type { Outline, ScriptJobRead, WrittenScript } from "@/lib/types";

function jobToScriptText(script: WrittenScript | null | undefined): string {
  if (!script) return "";
  return script.sections
    .map((s) => `## ${s.title}\n\n${s.content}\n`)
    .join("\n")
    .trim();
}

export default function ScriptEditorPage() {
  const params = useParams<{ id: string }>();
  const jobId = typeof params?.id === "string" ? params.id : "";

  const { push } = useToast();
  const [job, setJob] = useState<ScriptJobRead | null>(null);
  const [finalScript, setFinalScript] = useState<WrittenScript | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");

  const loadJob = useCallback(async (id: string) => {
    try {
      const data = await api.getScript(id);
      setJob(data);
      if (data.status === "completed" && data.final_script) {
        setFinalScript(data.final_script);
      }
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load script.";
      setError(message);
      push(message, "error");
      return null;
    }
  }, [push]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const load = async () => {
      const data = await loadJob(jobId);
      if (cancelled) return;
      if (data && (data.status === "pending" || data.status === "running")) {
        setLoading(true);
        try {
          await streamScriptEvents(jobId, (event) => {
            if (cancelled) return;
            if (event.event === "failed") {
              setError(event.error ?? "Script generation failed.");
              setLoading(false);
            }
          });
          const updated = await api.getScript(jobId);
          if (cancelled) return;
          setJob(updated);
          if (updated.status === "completed" && updated.final_script) {
            setFinalScript(updated.final_script);
          }
          setLoading(false);
        } catch (err) {
          if (cancelled) return;
          const message = err instanceof Error ? err.message : "Stream failed.";
          setError(message);
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [jobId, loadJob]);

  const retryJob = async () => {
    if (!jobId || loading) return;
    setLoading(true);
    setError(null);
    try {
      await api.retryScript(jobId);
      await streamScriptEvents(jobId, (event) => {
        if (event.event === "failed") {
          setError(event.error ?? "Retry failed.");
        }
      });
      const updated = await api.getScript(jobId);
      setJob(updated);
      if (updated.status === "completed" && updated.final_script) {
        setFinalScript(updated.final_script);
      } else if (updated.status === "failed") {
        setError(updated.error ?? "Retry failed.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Retry failed.";
      setError(message);
      push(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const regenerate = async (sectionType: string) => {
    if (!jobId) return;
    setRegenerating(sectionType);
    setError(null);
    try {
      const accepted = await api.regenerateSection(jobId, { section_type: sectionType, instruction: instruction.trim() || undefined });
      await streamScriptEvents(accepted.job_id, () => {});
      const updated = await api.getScript(accepted.job_id);
      setJob(updated);
      if (updated.status === "completed" && updated.final_script) {
        setFinalScript(updated.final_script);
      }
      setInstruction("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Regeneration failed.";
      setError(message);
      push(message, "error");
    } finally {
      setRegenerating(null);
    }
  };

  const copyScript = async () => {
    const text = jobToScriptText(finalScript);
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      push("Script copied to clipboard.", "success");
    } catch {
      push("Copy failed.", "error");
    }
  };

  const exportScript = async (format: string) => {
    if (!jobId) return;
    try {
      const blob = await api.exportScript(jobId, format);
      saveBlob(blob, `youtube_script_${jobId}.${format}`);
      push(`Export (${format}) downloaded.`, "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Export failed.";
      setError(message);
      push(message, "error");
    }
  };

  if (!jobId) {
    return (
      <div className="card">
        <h1 className="text-2xl font-semibold">Script Editor</h1>
        <p className="mt-2 text-muted-foreground">Missing script job id.</p>
        <Link href="/" className="btn-primary mt-4 inline-flex h-10 items-center">Back to New Script</Link>
      </div>
    );
  }

  const outline: Outline | null = job?.outline ?? null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Script Editor</h1>
          <p className="mt-2 font-mono text-sm text-muted-foreground">{jobId}</p>
        </div>
        {job ? <span className="rounded-full border px-3 py-1 text-xs uppercase tracking-wide">{job.status}</span> : null}
      </div>

      {error ? (
        <div className="card border-red-500/50">
          <h2 className="font-semibold text-red-600">Error</h2>
          <p className="mt-2 whitespace-pre-wrap">{error}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <button type="button" className="btn-primary" disabled={loading} onClick={() => void retryJob()}>
              Retry
            </button>
            <button type="button" className="btn-secondary" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {job ? (
        <div className="card space-y-2">
          <h2 className="font-semibold">Request</h2>
          <p className="text-sm">{job.topic}</p>
          {job.audience ? <p className="text-sm text-muted-foreground">Audience: {job.audience}</p> : null}
          {job.critique ? (
            <div className="mt-2 rounded border border-border p-3 text-sm">
              <p className="font-semibold">Critic passed: {String(job.critique.assessment.passed)}</p>
              <p className="mt-1 text-muted-foreground">{job.critique.assessment.feedback}</p>
              {job.critique.weak_sections ? <p className="mt-1 text-muted-foreground">Weak: {job.critique.weak_sections.join(", ")}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {outline ? (
        <div className="card space-y-4">
          <h2 className="font-semibold">Outline</h2>
          <OutlineView outline={outline} />
        </div>
      ) : null}

      {finalScript ? (
        <div className="card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Script · {finalScript.word_count} words</h2>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary" onClick={() => void copyScript()} disabled={!finalScript.sections.length}>
                Copy
              </button>
              <button type="button" className="btn-secondary" onClick={() => void exportScript("txt")}>Export TXT</button>
              <button type="button" className="btn-secondary" onClick={() => void exportScript("md")}>Export MD</button>
              <button type="button" className="btn-secondary" onClick={() => void exportScript("docx")}>Export DOCX</button>
              <button type="button" className="btn-secondary" onClick={() => void exportScript("pdf")}>Export PDF</button>
            </div>
          </div>
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
      ) : null}

      {finalScript && (
        <div className="card space-y-3">
          <h2 className="font-semibold">Regenerate section</h2>
          <div className="flex flex-wrap gap-2">
            {finalScript.sections.map((section) => (
              <button
                key={section.section_type}
                type="button"
                className="btn-secondary"
                disabled={regenerating !== null}
                onClick={() => void regenerate(section.section_type)}
              >
                {regenerating === section.section_type ? "Working…" : `Regenerate ${section.section_type.replace(/_/g, " ")}`}
              </button>
            ))}
          </div>
          <input
            className="input"
            placeholder="Optional instruction for the writer (e.g. make the hook more emotional)"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            aria-label="Regeneration instruction"
          />
        </div>
      )}

      {loading ? <p className="text-muted-foreground">Pipeline running…</p> : null}
    </div>
  );
}

function OutlineView({ outline }: { outline: Outline }) {
  const items: { label: string; value: unknown }[] = [
    { label: "Hook", value: outline.hook },
    { label: "Intro", value: outline.intro },
    { label: "Retention Loop", value: outline.retention_loop },
    { label: "CTA", value: outline.cta },
    { label: "Outro", value: outline.outro },
    ...(outline.main_points ?? []).map((m) => ({ label: `Main Point ${m.title}`, value: m })),
  ];
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label as string} className="rounded border border-border p-3">
          <h3 className="font-semibold">{item.label}</h3>
          <p className="text-sm text-muted-foreground">{String((item.value as { title?: string })?.title ?? "")}</p>
        </div>
      ))}
    </div>
  );
}
