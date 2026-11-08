"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useToast } from "@/hooks/use-toast";
import { clearApiKey, getApiKey, setApiKey } from "@/lib/api";

export default function SettingsPage() {
  const { push } = useToast();
  const [key, setKey] = useState("");
  const [current, setCurrent] = useState("");

  useEffect(() => {
    setCurrent(getApiKey());
  }, []);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed) {
      push("API key cannot be empty.", "error");
      return;
    }
    setApiKey(trimmed);
    setCurrent(trimmed);
    push("API key saved.", "success");
  };

  const onClear = () => {
    clearApiKey();
    setCurrent("");
    push("API key cleared.", "info");
  };

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-2 text-muted-foreground">Manage your YouTube Script Generator API key.</p>
      </div>

      <form className="card space-y-4" onSubmit={onSubmit}>
        <div>
          <label className="label" htmlFor="api-key">API Key</label>
          <input
            id="api-key"
            className="input"
            type="password"
            autoComplete="off"
            placeholder="Paste your backend API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Stored in your browser localStorage and sent as the <code className="font-mono">X-API-Key</code> header on every request.
          </p>
        </div>
        <div className="flex gap-3">
          <button type="submit" className="btn-primary">Save API Key</button>
          <button type="button" className="btn-secondary" onClick={onClear}>
            Clear
          </button>
        </div>
      </form>

      <div className="card">
        <h2 className="font-semibold">Current key</h2>
        <p className="mt-2 font-mono text-sm break-all">{current ? "••••••••••••" + current.slice(-4) : "None set"}</p>
      </div>
    </div>
  );
}
