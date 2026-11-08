export type ScriptStatus = "pending" | "running" | "completed" | "failed" | "draft" | "review" | "approved" | "published";

export type Tone = "educational" | "funny" | "storytelling" | "motivational";

export type ScriptLanguage = "English" | "Urdu" | "Roman Urdu" | "Hindi";

export type ScriptFormat = "long_form" | "shorts";

export type SectionType = "hook" | "intro" | "main_point" | "retention_loop" | "cta" | "outro";

export type ExportFormat = "txt" | "md" | "docx" | "pdf";

export interface OutlineSection {
  section_type: SectionType;
  title: string;
  key_points?: string[];
  estimated_duration_seconds?: number;
}

export interface Outline {
  hook: OutlineSection;
  intro: OutlineSection;
  main_points: OutlineSection[];
  retention_loop: OutlineSection;
  cta: OutlineSection;
  outro: OutlineSection;
}

export interface WriterSection {
  section_type: SectionType;
  title: string;
  content: string;
  b_roll_cues?: string[];
  on_screen_text?: string[];
  word_count?: number;
}

export interface WrittenScript {
  sections: WriterSection[];
  word_count: number;
}

export interface CriticAssessment {
  hook_strength: number;
  pacing: number;
  clarity: number;
  repetition: number;
  feedback?: string;
  passed?: boolean;
}

export interface CriticResult {
  assessment: CriticAssessment;
  weak_sections?: string[];
}

export interface ScriptRequest {
  topic: string;
  audience?: string;
  tone?: Tone;
  language?: ScriptLanguage;
  duration_minutes: number;
  format?: ScriptFormat;
}

export interface JobAccepted {
  job_id: string;
  status?: string;
}

export interface ScriptJobRead {
  id: string;
  status: ScriptStatus;
  topic: string;
  audience?: string;
  tone?: Tone;
  language?: ScriptLanguage;
  duration_minutes: number;
  format?: ScriptFormat;
  outline?: Outline | null;
  final_script?: WrittenScript | null;
  critique?: CriticResult | null;
  error?: string | null;
  model_usage?: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface DailyQuota {
  owner: string;
  used: number;
  limit: number;
  remaining: number | null;
  unlimited: boolean;
  resets_at: string;
}

export interface ScriptSummary {
  id: string;
  topic: string;
  status: ScriptStatus;
  format?: ScriptFormat;
  duration_minutes: number;
  created_at: string;
}

export interface PipelineEvent {
  event: string;
  job_id: string;
  agent?: string | null;
  section?: WriterSection | null;
  assessment?: CriticResult | null;
  weak_sections?: string[] | null;
  script?: WrittenScript | null;
  error?: string | null;
}

export interface RegenerateSectionRequest {
  section_type: SectionType;
  instruction?: string;
}

export interface HookVariant {
  text: string;
  style: string;
  angle: string;
}

export interface HookEvaluation {
  hook_index: number;
  hook_strength: number;
  reasoning: string;
}

export interface HookTestPlan {
  job_id: string;
  baseline_hook: string;
  candidates: HookVariant[];
  evaluations: HookEvaluation[];
  metrics: string[];
  winner: string | null;
}

export interface HookTestResult {
  job_id: string;
  winner_hook: string;
  metrics: Record<string, unknown>;
  notes: string;
}

export interface HookTestResultCreate {
  winner_hook: string;
  metrics: Record<string, unknown>;
  notes: string;
}

export interface Shot {
  section_type: string;
  shot_type: string;
  visual_description: string;
  b_roll_keywords: string[];
  on_screen_text: string;
  estimated_duration_seconds: number;
}

export interface Storyboard {
  job_id: string;
  shots: Shot[];
}

export interface TTSRequest {
  section_type: string;
  voice: string;
}

export interface DubRequest {
  language: string;
}

export interface DubScript {
  language: string;
  source_language: string;
  sections: unknown[];
  notes: string;
}

export interface Trend {
  keyword: string;
  score: number;
  reason: string;
  source: string;
}

export interface PlanCreate {
  niche: string;
  goal?: string;
  episodes?: number;
}

export interface PlanItem {
  id: string;
  title: string;
  angle: string;
  target_keyword: string;
  format: string;
  publish_date: string;
  estimated_duration_minutes: number;
  notes: string;
}

export interface SeriesPlan {
  id: string;
  niche: string;
  goal: string;
  series_title: string;
  episodes: PlanItem[];
}

export interface PlanItemUpdate {
  title?: string;
  angle?: string;
  target_keyword?: string;
  format?: string;
  publish_date?: string;
  estimated_duration_minutes?: number;
  notes?: string;
}

export interface CompetitorGapRequest {
  urls: string[];
}

export interface Gap {
  area: string;
  gap_description: string;
  suggested_angle: string;
  difficulty: number;
}

export interface CompetitorGap {
  competitors: unknown[];
  gaps: Gap[];
  suggestions: unknown[];
}

export interface BillingPlan {
  [key: string]: unknown;
}

export interface BillingUsage {
  [key: string]: unknown;
}
