import type {
  DailyQuota,
  JobAccepted,
  PipelineEvent,
  ScriptJobRead,
  ScriptRequest,
  ScriptSummary,
  SeriesPlan,
  Trend,
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_KEY_STORAGE_KEY = "ytg_api_key";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getApiKey(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function clearApiKey(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(API_KEY_STORAGE_KEY);
}

export function getAuthHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
}

function buildUrl(path: string, query?: Record<string, string>): string {
  const qs = query ? `?${new URLSearchParams(query).toString()}` : "";
  return `${API_BASE_URL}${path}${qs}`;
}

async function request<T>(path: string, init?: { method?: string; body?: unknown; query?: Record<string, string> }): Promise<T> {
  const res = await fetch(buildUrl(path, init?.query), {
    method: init?.method ?? "GET",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 401) {
    throw new ApiError("Unauthorized: invalid or missing API key. Please add your API key in Settings.", 401);
  }
  if (res.status === 204) return undefined as T;
  const data = (await res.json().catch(() => null)) as { detail?: string } | null;
  if (res.status === 429) {
    // Preserve backend quota messages ("Daily generation limit reached ... resets at ...")
    throw new ApiError(data?.detail ?? "Rate limit exceeded. Please wait a minute and try again.", 429);
  }
  if (!res.ok) {
    throw new ApiError(data?.detail ?? `Request failed with status ${res.status}`, res.status);
  }
  return (data ?? {}) as T;
}

/** Health check used by the cold-start banner. Never throws. */
export async function checkBackendHealth(timeoutMs = 5000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal, cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  getQuota: () => request<DailyQuota>("/v1/scripts/quota"),
  generateScript: (body: ScriptRequest) => request<JobAccepted>("/v1/scripts/generate", { method: "POST", body }),
  retryScript: (jobId: string) => request<JobAccepted>(`/v1/scripts/${jobId}/retry`, { method: "POST" }),
  listScripts: () => request<ScriptSummary[]>("/v1/scripts"),
  getScript: (jobId: string) => request<ScriptJobRead>(`/v1/scripts/${jobId}`),
  regenerateSection: (jobId: string, body: { section_type: string; instruction?: string }) =>
    request<JobAccepted>(`/v1/scripts/${jobId}/regenerate-section`, { method: "POST", body }),
  exportScript: async (jobId: string, format: string): Promise<Blob> => {
    const res = await fetch(buildUrl(`/v1/scripts/${jobId}/export`, { format }), {
      method: "GET",
      headers: { ...getAuthHeaders() },
    });
    if (res.status === 401) throw new ApiError("Unauthorized: invalid or missing API key. Please add your API key in Settings.", 401);
    if (res.status === 429) throw new ApiError("Rate limit exceeded. Please wait a minute and try again.", 429);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new ApiError(data?.detail ?? `Export failed with status ${res.status}`, res.status);
    }
    return res.blob();
  },
  getTrends: (niche?: string) => request<Trend[]>(`/v1/trends${niche ? `?niche=${encodeURIComponent(niche)}` : ""}`),
  refreshTrends: (niche?: string) =>
    request<unknown>("/v1/trends/refresh", { method: "POST", query: niche ? { niche } : undefined }),
  createPlan: (body: { niche: string; goal?: string; episodes?: number }) => request<SeriesPlan>("/v1/plans", { method: "POST", body }),
  getPlan: (planId: string) => request<SeriesPlan>(`/v1/plans/${planId}`),
  createStoryboard: (jobId: string) => request<{ job_id: string; shots: unknown[] }>(`/v1/scripts/${jobId}/storyboard`, { method: "POST" }),
  getStoryboard: (jobId: string) => request<{ job_id: string; shots: unknown[] }>(`/v1/scripts/${jobId}/storyboard`),
  createHookTests: (jobId: string) => request<unknown>(`/v1/scripts/${jobId}/hook-tests`, { method: "POST" }),
  getHookTestResult: (jobId: string) => request<unknown>(`/v1/scripts/${jobId}/hook-tests/results`),
  logHookTestResult: (jobId: string, body: Record<string, unknown>) =>
    request<unknown>(`/v1/scripts/${jobId}/hook-tests/results`, { method: "POST", body }),
  dubScript: (jobId: string, body: { language: string }) => request<unknown>(`/v1/scripts/${jobId}/dub`, { method: "POST", body }),
  generateTts: (jobId: string, body: { section_type: string; voice: string }) => request<unknown>(`/v1/scripts/${jobId}/tts`, { method: "POST", body }),
  listBillingPlans: () => request<unknown[]>("/v1/billing/plans"),
  getBillingUsage: () => request<unknown>("/v1/billing/usage"),
  subscribe: (plan?: string, userId?: string) =>
    request<unknown>(`/v1/billing/subscribe?plan=${encodeURIComponent(plan ?? "pro")}&user_id=${encodeURIComponent(userId ?? "user-1")}`, { method: "POST" }),
};

export async function streamScriptEvents(
  jobId: string,
  onEvent: (event: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/v1/scripts/${jobId}/stream`, {
    headers: { Accept: "text/event-stream", ...getAuthHeaders() },
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(data?.detail ?? `Stream failed with status ${res.status}`, res.status);
  }
  if (!res.body) throw new ApiError("No response body for SSE stream", 200);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName: string | null = null;
  let dataStr = "";

  const dispatch = () => {
    if (eventName && dataStr) {
      try {
        onEvent(JSON.parse(dataStr) as PipelineEvent);
      } catch {
        // ignore malformed events
      }
    }
    eventName = null;
    dataStr = "";
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const lines = block.split("\n");
      let name: string | null = null;
      let data = "";
      for (const line of lines) {
        const t = line.trim();
        if (t.startsWith("event:")) name = t.slice(6).trim();
        else if (t.startsWith("data:")) data = t.slice(5).trim();
      }
      if (name) eventName = name;
      if (data) dataStr = data;
      if (eventName && dataStr) dispatch();
    }
  }
  dispatch();
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
