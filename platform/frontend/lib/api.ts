/** Typed fetch helpers for the FastAPI backend (proxied via next.config rewrites). */

export interface AgentStatus {
  name: string;
  status: string;
  consultations: number;
}

export interface AgentsStatus {
  agents: AgentStatus[];
  system: { llm: string; model: string; provider: string; local_only: boolean };
}

export interface CriticalPatient {
  id: string;
  name: string;
  risk_level: "high" | "medium";
  top_flag: string | null;
  flag_count: number;
}

export interface DashboardStats {
  critical_patients: CriticalPatient[];
  critical_count: number;
  at_risk_count: number;
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
  acted_on: boolean | null;
  acted_at: string | null;
  outcome: "improved" | "not_improved" | "unclear" | null;
  outcome_at: string | null;
}

export interface RecommendationStats {
  total: number;
  acted_on: number;
  improved: number;
}

export interface DrugInteraction {
  pair: [string, string];
  severity: string;
  effect: string;
  recommendation: string;
}

export interface EvidenceCategory {
  slug: string;
  label: string;
  count: number;
}

export interface EvidenceItem {
  id: string;
  title: string;
  organization: string | null;
  year: number | null;
  excerpt: string;
  citation: string;
}

export interface DrugCheckResult {
  medications_checked: string[];
  interactions_found: number;
  interactions: DrugInteraction[];
  disclaimer: string;
}

export interface UserOut {
  id: string;
  email: string;
  name: string;
  role: "clinician" | "patient";
  patient_id: string | null;
}

export interface AuthResponse {
  access_token: string;
  user: UserOut;
}

// --- Scheduling -------------------------------------------------------

export interface AvailabilityRule {
  id: string;
  clinician_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  timezone: string;
  slot_minutes: number;
  effective_from: string | null;
  effective_to: string | null;
  active: boolean;
}

export interface AvailabilityException {
  id: string;
  clinician_id: string;
  start_at: string;
  end_at: string;
  kind: "block" | "open";
  reason: string;
}

export interface Availability {
  rules: AvailabilityRule[];
  exceptions: AvailabilityException[];
}

export interface Slot {
  start_at: string;
  end_at: string;
}

export interface Appointment {
  id: string;
  clinician_id: string;
  patient_id: string;
  patient_name?: string;
  start_at: string;
  end_at: string;
  status: "booked" | "completed" | "cancelled" | "no_show";
  mode: "in_person" | "telehealth";
  reason: string;
  notes?: string;
  cancellation_reason: string;
  series_id?: string | null;
}

export interface AppNotification {
  id: string;
  type: "appointment_booked" | "result_shared" | "waitlist_match";
  message: string;
  related_appointment_id?: string | null;
  read_at: string | null;
  created_at: string;
}

export interface TodayAgenda {
  date: string;
  count: number;
  next_at: string | null;
  items: { id: string; start_at: string; end_at: string; patient_name: string; reason: string }[];
}

// --- Results ------------------------------------------------------------

export interface ShareableEvent extends TimelineEvent {
  timeline_event_id: number;
  already_shared: boolean;
}

export interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface ResultShare {
  id: string;
  status: "sent" | "revoked";
  message: string;
  shared_at: string;
  viewed_at: string | null;
  event: TimelineEvent;
  attachments: Attachment[];
}

// --- Portal ---------------------------------------------------------------

export interface PortalMe {
  id: string;
  name: string;
  age: number;
  sex: string;
  conditions: string[];
  medications: string[];
  allergies: string[];
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

/** Carries the HTTP status so callers can tell a 403 ("not available for
 * your account") apart from any other failure, without parsing message
 * text. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Not authenticated");
  }
  if (res.status === 403) {
    throw new ApiError(403, "This isn't available for your account.");
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  if (res.status === 204) return undefined as T;
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

async function patch<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    })
  );
}

/** DELETE expecting a 204 No Content response. */
async function del(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE", headers: authHeaders() });
  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Not authenticated");
  }
  if (res.status === 403) throw new ApiError(403, "This isn't available for your account.");
  if (!res.ok) throw new ApiError(res.status, await res.text());
}

/** POST expecting a 204 No Content response (no JSON body to parse). */
async function postNoContent(path: string, body: unknown): Promise<void> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("401: not authenticated");
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
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
  agentsStatus: () => get<AgentsStatus>("/api/agents/status"),
  patients: (sort?: "risk") => get<PatientSummary[]>(`/api/patients${sort ? `?sort=${sort}` : ""}`),
  patient: (id: string) => get<Patient>(`/api/patients/${id}`),
  history: () => get<HistoryItem[]>("/api/agents/history"),
  recommendationStats: () => get<RecommendationStats>("/api/agents/recommendations/stats"),
  markActedOn: (id: string, acted_on: boolean) =>
    patch<HistoryItem>(`/api/agents/history/${id}`, { acted_on }),
  markOutcome: (id: string, outcome: "improved" | "not_improved" | "unclear") =>
    patch<HistoryItem>(`/api/agents/history/${id}`, { outcome }),
  checkDrugInteractions: (medications: string[]) =>
    post<DrugCheckResult>("/api/medical/drugs/check", { medications }),
  consult: (body: { query: string; patient_id?: string; context?: Record<string, unknown> }) =>
    post<ConsultResponse>("/api/agents/consult", body),
  analyzeImage: (body: { image_path: string; modality: string; target?: string }) =>
    post<Record<string, unknown>>("/api/medical/imaging/analyze", body),
  describeImage: (body: { image_path: string; clinical_focus?: string }) =>
    post<DescribeImageResponse>("/api/medical/imaging/describe", body),
  imagePreviewUrl: (path: string) =>
    `/api/medical/imaging/preview?path=${encodeURIComponent(path)}`,
  detectModality: (imagePath: string) =>
    post<{ modality: string }>("/api/medical/imaging/detect-modality", { image_path: imagePath }),
  addTimelineEvent: (patientId: string, body: { type: string; title: string; detail?: string }) =>
    post<TimelineEvent>(`/api/patients/${patientId}/timeline`, body),
  uploadImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<{ path: string }>("/api/medical/imaging/upload", form);
  },
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
  evidenceCategories: () => get<EvidenceCategory[]>("/api/rag/categories"),
  evidenceByCategory: (slug: string) => get<EvidenceItem[]>(`/api/rag/categories/${slug}`),
  updateProfile: (body: { email: string; name: string }) => patch<UserOut>("/api/auth/me", body),
  changePassword: (body: { current_password: string; new_password: string }) =>
    postNoContent("/api/auth/change-password", body),
  createInvite: (patientId: string) =>
    post<{ invite_id: string; code: string; expires_at: string }>(
      `/api/patients/${patientId}/invites`,
      {}
    ),

  // --- Scheduling ---------------------------------------------------------
  getAvailability: () => get<Availability>("/api/scheduling/availability"),
  createAvailabilityRule: (body: {
    weekday: number;
    start_time: string;
    end_time: string;
    timezone?: string;
    slot_minutes?: number;
  }) => post<AvailabilityRule>("/api/scheduling/availability", body),
  updateAvailabilityRule: (ruleId: string, body: Partial<AvailabilityRule>) =>
    patch<AvailabilityRule>(`/api/scheduling/availability/${ruleId}`, body),
  deleteAvailabilityRule: (ruleId: string) => del(`/api/scheduling/availability/${ruleId}`),
  createException: (body: { start_at: string; end_at: string; kind: "block" | "open"; reason?: string }) =>
    post<AvailabilityException>("/api/scheduling/exceptions", body),
  deleteException: (exceptionId: string) => del(`/api/scheduling/exceptions/${exceptionId}`),
  getSlots: (clinicianId: string, from: string, to: string) =>
    get<{ clinician_id: string; slots: Slot[] }>(
      `/api/scheduling/slots?clinician_id=${encodeURIComponent(clinicianId)}&from=${from}&to=${to}`
    ),
  listAppointments: (params?: { from?: string; to?: string; status?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return get<Appointment[]>(`/api/scheduling/appointments${qs ? `?${qs}` : ""}`);
  },
  bookAppointment: (
    body: { clinician_id: string; patient_id: string; start_at: string; mode?: string; reason?: string },
    force = false
  ) => post<Appointment>(`/api/scheduling/appointments${force ? "?force=true" : ""}`, body),
  updateAppointment: (
    appointmentId: string,
    body: { start_at?: string; status?: string; mode?: string; notes?: string }
  ) => patch<Appointment>(`/api/scheduling/appointments/${appointmentId}`, body),
  cancelAppointment: (appointmentId: string, reason?: string) =>
    del(`/api/scheduling/appointments/${appointmentId}${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`),
  agendaToday: () => get<TodayAgenda>("/api/scheduling/agenda/today"),

  // --- Results -------------------------------------------------------------
  shareableEvents: (patientId: string) => get<ShareableEvent[]>(`/api/results/shareable/${patientId}`),
  createShare: (body: { patient_id: string; timeline_event_id: number; message?: string }) =>
    post<ResultShare>("/api/results/shares", body),
  updateShareMessage: (shareId: string, message: string) =>
    patch<ResultShare>(`/api/results/shares/${shareId}`, { message }),
  uploadAttachment: (shareId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<Attachment>(`/api/results/shares/${shareId}/attachments`, form);
  },
  listShares: (patientId?: string) =>
    get<ResultShare[]>(`/api/results/shares${patientId ? `?patient_id=${patientId}` : ""}`),
  getShare: (shareId: string) => get<ResultShare>(`/api/results/shares/${shareId}`),
  revokeShare: (shareId: string) => del(`/api/results/shares/${shareId}`),
  // Authenticated download: the token lives in localStorage, not a cookie,
  // so a plain `<a href>` to this path would 401 — fetch as a Blob and
  // trigger the download client-side instead (same pattern as
  // `exportConsultation`).
  downloadAttachment: (attachmentId: string) => getBlob(`/api/results/attachments/${attachmentId}/download`),

  // --- Portal ---------------------------------------------------------------
  portalMe: () => get<PortalMe>("/api/portal/me"),
  portalTimeline: () => get<{ patient_id: string; events: TimelineEvent[] }>("/api/portal/timeline"),
  portalLabs: () => get<{ patient_id: string; lab_results: Record<string, string> }>("/api/portal/labs"),
  claimInvite: (body: { code: string; email: string; name: string; password: string }) =>
    post<AuthResponse>("/api/auth/portal/claim", body),

  // --- Notifications ---------------------------------------------------------
  listNotifications: () => get<AppNotification[]>("/api/notifications"),
  unreadNotificationCount: () => get<{ count: number }>("/api/notifications/unread-count"),
  markNotificationRead: (notificationId: string) =>
    postNoContent(`/api/notifications/${notificationId}/read`, {}),
};
