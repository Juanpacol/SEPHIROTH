/** Typed fetch helpers for the FastAPI backend (proxied via next.config rewrites). */

export interface Kpi {
  label: string;
  value: number;
  delta: string;
  trend: "up" | "down";
}

export interface AgentStatus {
  name: string;
  status: string;
  consultations: number;
}

export interface DashboardStats {
  kpis: Kpi[];
  agents: AgentStatus[];
  system: { ollama: string; model: string; local_only: boolean };
}

export interface PatientSummary {
  id: string;
  name: string;
  age: number;
  sex: string;
  medical_record_number: string;
  conditions: string[];
  status: string;
  risk_level?: "high" | "medium" | "low";
}

export interface RiskFlag {
  source: "lab" | "drug";
  label: string;
  severity: "high" | "medium";
  detail: string;
}

export interface TimelineEvent {
  date: string;
  type: string;
  title: string;
  detail: string;
  ai_generated?: boolean;
}

export interface Patient extends PatientSummary {
  medications: string[];
  allergies: string[];
  timeline: TimelineEvent[];
  lab_results: Record<string, string>;
  risk_flags?: RiskFlag[];
}

export interface ToolCall {
  agent?: string;
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface CitationReport {
  verified?: string[];
  fabricated?: string[];
}

export interface ExplanationStep {
  agent: string;
  action: string;
  tool: string;
}

export interface Explanation {
  steps: ExplanationStep[];
  citations_verified: number;
  citations_removed: number;
}

export interface ConsultResponse {
  id?: string;
  answer: string;
  agents_involved: string[];
  tool_calls: ToolCall[];
  citation_report?: CitationReport;
  explanation?: Explanation;
  disclaimer?: string;
}

export interface HistoryItem extends ConsultResponse {
  id: string;
  query: string;
  patient_id: string | null;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  user: { id: string; email: string; name: string };
}

export interface DescribeImageResponse {
  status?: string;
  description?: string | null;
  model?: string;
  message?: string;
  error?: string;
  requires_professional_review?: boolean;
}

import { authHeaders, redirectToLogin } from "./auth";

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("401: not authenticated");
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { headers: authHeaders() }));
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    })
  );
}

/** Multipart POST — the browser sets the Content-Type boundary itself. */
async function postForm<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(path, { method: "POST", headers: authHeaders(), body: form }));
}

/** Authenticated binary download (e.g. PDF export). */
async function getBlob(path: string): Promise<Blob> {
  const res = await fetch(path, { headers: authHeaders() });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("401: not authenticated");
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.blob();
}

export const api = {
  register: (body: { email: string; name: string; password: string }) =>
    post<AuthResponse>("/api/auth/register", body),
  login: (body: { email: string; password: string }) =>
    post<AuthResponse>("/api/auth/login", body),
  dashboardStats: () => get<DashboardStats>("/api/dashboard/stats"),
  patients: () => get<PatientSummary[]>("/api/patients"),
  patient: (id: string) => get<Patient>(`/api/patients/${id}`),
  history: () => get<HistoryItem[]>("/api/agents/history"),
  consult: (body: { query: string; patient_id?: string; context?: Record<string, unknown> }) =>
    post<ConsultResponse>("/api/agents/consult", body),
  analyzeImage: (body: { image_path: string; modality: string; target?: string }) =>
    post<Record<string, unknown>>("/api/medical/imaging/analyze", body),
  describeImage: (body: { image_path: string; clinical_focus?: string }) =>
    post<DescribeImageResponse>("/api/medical/imaging/describe", body),
  imagePreviewUrl: (path: string) =>
    `/api/medical/imaging/preview?path=${encodeURIComponent(path)}`,
  uploadNote: (patientId: string, file: File, noteDate?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (noteDate) form.append("note_date", noteDate);
    return postForm<{ events_added: unknown[]; source_file: string }>(
      `/api/patients/${patientId}/notes/upload`,
      form
    );
  },
  exportConsultation: (id: string) => getBlob(`/api/agents/history/${id}/export`),
  searchEvidence: (q: string) =>
    get<{ results: { content: string; citation: string; score: number }[] }>(
      `/api/rag/search?q=${encodeURIComponent(q)}`
    ),
};
