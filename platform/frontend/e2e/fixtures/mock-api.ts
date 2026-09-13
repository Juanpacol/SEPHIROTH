import type { Page, Route } from "@playwright/test";

/** Serves the backend so the layout tests look at real content.
 *
 * This is load-bearing, not convenience. Without it every page renders its
 * empty or error state — a single short line of text that overflows nothing and
 * has no controls to measure — and the whole suite goes green having verified
 * precisely nothing. Any page added to the matrix needs its endpoints here.
 *
 * Matching is longest-prefix, so a specific path wins over a general one
 * regardless of declaration order.
 */

/** A timestamp in the backend's own format: naive, no trailing `Z`.
 *
 * Both halves matter. The `Z` has to go because the app re-appends one
 * (`components/schedule/time.ts`) — `"...Z" + "Z"` parses as Invalid Date and
 * every appointment silently vanishes from the grid. And the dates are relative
 * to today, not a fixed month, because /schedule only ever queries the current
 * week: pinned fixtures would leave the page empty and the layout assertions
 * would pass having measured nothing. */
const iso = (daysFromNow: number, hour = 9): string => {
  // Built from local calendar parts, never from `toISOString()`: the app reads
  // these as wall-clock times, and a UTC round-trip shifts "today" by a day for
  // anyone west of Greenwich — which silently moves every fixture appointment
  // off the day the test expects to find it on.
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:00:00`;
};

/** Long, realistic strings on purpose: a name that fits is not a test. */
const PATIENTS = [
  {
    id: "p-001",
    name: "María Fernanda Restrepo Villegas",
    age: 67,
    sex: "F",
    medical_record_number: "MRN-2024-0001",
    conditions: ["Type 2 diabetes mellitus", "Chronic kidney disease stage 3b", "Hypertension"],
    status: "active",
    risk_level: "high" as const,
  },
  {
    id: "p-002",
    name: "Juan Esteban Ocampo",
    age: 54,
    sex: "M",
    medical_record_number: "MRN-2024-0002",
    conditions: ["Atrial fibrillation", "Heart failure with reduced ejection fraction"],
    status: "active",
    risk_level: "medium" as const,
  },
  {
    id: "p-003",
    name: "Lucía Gómez",
    age: 31,
    sex: "F",
    medical_record_number: "MRN-2024-0003",
    conditions: ["Asthma"],
    status: "active",
    risk_level: "low" as const,
  },
];

const ALERTS = [
  {
    id: "a-001",
    patient_id: "p-001",
    category: "lab",
    severity: "critical" as const,
    status: "active" as const,
    title: "Potassium 6.4 mmol/L — severe hyperkalaemia",
    detail:
      "Serum potassium rose from 5.1 to 6.4 mmol/L in 48 hours on a patient already taking spironolactone and lisinopril.",
    source: "lab_rule",
    assigned_to_user_id: null,
    due_at: iso(0, 14),
    reviewed_at: null,
    reviewed_by: null,
    resolved_at: null,
    escalated_at: null,
    created_at: iso(-1),
  },
  {
    id: "a-002",
    patient_id: "p-002",
    category: "drug",
    severity: "high" as const,
    status: "active" as const,
    title: "Amiodarone + warfarin interaction",
    detail: "Amiodarone potentiates warfarin; INR monitoring interval should be shortened.",
    source: "drug_safety",
    assigned_to_user_id: null,
    due_at: null,
    reviewed_at: null,
    reviewed_by: null,
    resolved_at: null,
    escalated_at: null,
    created_at: iso(-2),
  },
];

const APPROVALS = [
  {
    id: "ap-001",
    workflow_step_id: null,
    patient_id: "p-001",
    patient_name: PATIENTS[0].name,
    action_type: "patient_message",
    instructions: "Explain the potassium result and the diet change in plain language.",
    status: "pending" as const,
    draft_text:
      "Your latest blood test showed a high potassium level. Please avoid bananas, oranges and salt substitutes until we repeat the test on Thursday, and call us if you feel weak or notice an irregular heartbeat.",
    draft_source: "llm" as const,
    draft_model: "gemini-flash-latest",
    final_text: "",
    edited: false,
    assigned_to_user_id: null,
    expires_at: iso(2),
    reviewed_by: null,
    reviewed_at: null,
    reject_reason: "",
    created_at: iso(-1),
  },
  {
    id: "ap-002",
    workflow_step_id: null,
    patient_id: "p-002",
    patient_name: PATIENTS[1].name,
    action_type: "referral_letter",
    instructions: null,
    status: "pending" as const,
    draft_text: "Referral to cardiology for rate-control review.",
    draft_source: "template" as const,
    draft_model: null,
    final_text: "",
    edited: false,
    assigned_to_user_id: null,
    expires_at: null,
    reviewed_by: null,
    reviewed_at: null,
    reject_reason: "",
    created_at: iso(-3),
  },
];

const ACTION_ITEMS = [
  {
    category: "alert" as const,
    severity: "critical" as const,
    patient_id: "p-001",
    patient_name: PATIENTS[0].name,
    title: "Severe hyperkalaemia",
    detail: "Potassium 6.4 mmol/L, up from 5.1 in 48 hours.",
  },
  {
    category: "lab" as const,
    severity: "high" as const,
    patient_id: "p-002",
    patient_name: PATIENTS[1].name,
    test_name: "INR",
    value: 4.8,
    unit: "",
  },
  {
    category: "followup" as const,
    severity: "medium" as const,
    patient_id: "p-003",
    patient_name: PATIENTS[2].name,
    days_late: 12,
  },
];


const APPOINTMENTS = [
  {
    id: "ap-1",
    clinician_id: "u-clinician",
    patient_id: "p-001",
    patient_name: PATIENTS[0].name,
    start_at: iso(0, 14),
    end_at: iso(0, 15),
    status: "booked" as const,
    mode: "in_person" as const,
    reason: "Renal function review after potassium spike",
    cancellation_reason: "",
    series_id: null,
    confirmed_at: null,
  },
  {
    id: "ap-2",
    clinician_id: "u-clinician",
    patient_id: "p-002",
    patient_name: PATIENTS[1].name,
    start_at: iso(1, 10),
    end_at: iso(1, 11),
    status: "booked" as const,
    mode: "telehealth" as const,
    reason: "Anticoagulation follow-up",
    cancellation_reason: "",
    series_id: null,
    confirmed_at: iso(-1),
  },
];

const RESULT_REVIEWS = [
  {
    id: "rr-1",
    result_type: "lab" as const,
    result_id: "lab-1",
    patient_id: "p-001",
    patient_name: PATIENTS[0].name,
    status: "received",
    severity: "critical",
    classification_reason: "Potassium 6.4 mmol/L is above the critical threshold of 6.0 mmol/L.",
    disposition: null,
    note: "",
    reviewed_at: null,
    reviewed_by: null,
    share_id: null,
    task_id: null,
    closed_at: null,
    created_at: iso(-1),
    needs_communication: true,
    closable: false,
    result: {
      kind: "lab",
      test_name: "Potassium",
      value: 6.4,
      unit: "mmol/L",
      reference_low: 3.5,
      reference_high: 5.1,
      taken_at: iso(-1),
    },
  },
];

const TIMELINE = [
  {
    date: iso(-4),
    type: "lab",
    title: "Comprehensive metabolic panel",
    detail: "Potassium 6.4 mmol/L, creatinine 2.1 mg/dL, eGFR 28 mL/min/1.73m².",
  },
  {
    date: iso(-30),
    type: "note",
    title: "Nephrology follow-up",
    detail: "Discussed progression of chronic kidney disease and reviewed the medication list.",
  },
];

/** Longest-prefix wins, so ordering here is irrelevant. */
const ROUTES: Record<string, unknown> = {
  "/api/dashboard/stats": {
    critical_patients: PATIENTS.filter((p) => p.risk_level !== "low").map((p, i) => ({
      id: p.id,
      name: p.name,
      risk_level: p.risk_level,
      priority_score: 90 - i * 20,
      top_flag: "Potassium 6.4 mmol/L",
      flag_count: 3 - i,
    })),
    critical_count: 1,
    moderate_count: 1,
    stable_count: 1,
    at_risk_count: 2,
    max_priority_score: 90,
    avg_priority_score: 55,
  },
  "/api/dashboard/action-items": { items: ACTION_ITEMS, total_count: ACTION_ITEMS.length },
  "/api/patients": PATIENTS,
  "/api/alerts": ALERTS,
  "/api/approvals/count": { count: APPROVALS.length },
  "/api/approvals": APPROVALS,
  "/api/notifications/unread-count": { count: 2 },
  "/api/notifications": [
    {
      id: "n-001",
      type: "result_shared",
      message: "A new lab result was shared with María Fernanda Restrepo Villegas.",
      related_appointment_id: null,
      read_at: null,
      created_at: iso(-1),
    },
  ],
  "/api/scheduling/appointments": APPOINTMENTS,
  "/api/scheduling/availability": { rules: [], exceptions: [] },
  "/api/scheduling/slots": [],
  "/api/results/shares/rs-001": {
    id: "rs-001",
    patient_id: "p-001",
    status: "sent" as const,
    message:
      "Your potassium came back high. I have stopped one of your tablets — please read the note below and book a repeat test.",
    shared_at: iso(-1),
    viewed_at: null,
    event: TIMELINE[0],
    attachments: [],
  },
  "/api/results/shares": [
    {
      id: "rs-001",
      patient_id: "p-001",
      status: "sent" as const,
      message: "Your potassium came back high.",
      shared_at: iso(-1),
      viewed_at: null,
      event: TIMELINE[0],
      attachments: [],
    },
  ],
  "/api/results/inbox": { items: RESULT_REVIEWS },
  "/api/patients/p-001": {
    ...PATIENTS[0],
    medications: ["Lisinopril 10 mg daily", "Spironolactone 25 mg daily", "Metformin 1 g twice daily"],
    allergies: ["Penicillin"],
    timeline: TIMELINE,
    lab_results: { Potassium: "6.4 mmol/L", Creatinine: "2.1 mg/dL", HbA1c: "8.2 %" },
    risk_flags: [
      {
        source: "lab" as const,
        label: "Severe hyperkalaemia",
        severity: "high" as const,
        detail: "Potassium 6.4 mmol/L with concurrent ACE inhibitor and aldosterone antagonist.",
      },
    ],
  },
  "/api/patients/p-001/labs": {
    patient_id: "p-001",
    tests: [
      {
        test_name: "Potassium",
        unit: "mmol/L",
        reference_low: 3.5,
        reference_high: 5.1,
        entries: [
          { value: 4.8, taken_at: iso(-60) },
          { value: 5.1, taken_at: iso(-30) },
          { value: 6.4, taken_at: iso(-1) },
        ],
      },
    ],
  },
  "/api/medical/imaging/recent": [],
  "/api/rag/categories": [
    { slug: "endocrinology", label: "Endocrinology", count: 12 },
    { slug: "nephrology", label: "Nephrology", count: 7 },
  ],
  "/api/portal/me": {
    id: "p-001",
    name: PATIENTS[0].name,
    age: PATIENTS[0].age,
    sex: PATIENTS[0].sex,
    conditions: PATIENTS[0].conditions,
    medications: ["Lisinopril 10 mg daily", "Metformin 1 g twice daily"],
    allergies: ["Penicillin"],
  },
  "/api/portal/timeline": { patient_id: "p-001", events: TIMELINE },
  "/api/portal/labs": { patient_id: "p-001", lab_results: { Potassium: "6.4 mmol/L" } },
  "/api/encounters/vitals/spec": { vitals: [], specialties: ["internal_medicine"] },
  "/api/encounters/e-001": {
    id: "e-001",
    patient_id: "p-001",
    patient_name: PATIENTS[0].name,
    clinician_id: "u-clinician",
    appointment_id: null,
    specialty: "internal_medicine",
    status: "draft" as const,
    chief_complaint: "Weakness and palpitations for two days",
    vitals: { systolic: 158, diastolic: 94, heart_rate: 58 },
    vital_findings: [
      {
        key: "systolic",
        label: "Blood pressure",
        display: "158/94 mmHg",
        severity: "high" as const,
        detail: "Stage 2 hypertension on a patient already taking an ACE inhibitor.",
      },
    ],
    subjective: "Two days of generalised weakness with intermittent palpitations.",
    objective: "Alert, oriented. Irregular pulse. No peripheral oedema.",
    assessment: "Severe hyperkalaemia secondary to combined RAAS blockade and declining renal function.",
    plan: "Hold spironolactone, repeat potassium in 24 hours, ECG today.",
    patient_instructions: "Stop the water pill until we call you, and go to A&E if you feel faint.",
    note_source: "llm" as const,
    note_model: "gemini-flash-latest",
    editable: true,
    signable: true,
    started_at: iso(0, 9),
    signed_at: null,
    signed_by: null,
    amended_at: null,
    amendment_reason: "",
    clinical_note_id: null,
    orders: [
      { id: "o-1", kind: "lab" as const, detail: "Basic metabolic panel", due_in_days: 1, task_id: null },
    ],
    template: { subjective: "", objective: "", assessment: "", plan: "" },
  },
  "/api/preferences": {},
  "/api/auth/me": {
    id: "u-clinician",
    email: "clinician@example.test",
    name: "Dr. Ana Ruiz",
    role: "clinician",
    patient_id: null,
  },
};

function bodyFor(pathname: string): unknown | undefined {
  const match = Object.keys(ROUTES)
    .filter((prefix) => pathname === prefix || pathname.startsWith(prefix + "/") || pathname.startsWith(prefix + "?"))
    .sort((a, b) => b.length - a.length)[0];
  return match === undefined ? undefined : ROUTES[match];
}

export async function mockApi(page: Page): Promise<void> {
  await page.route("**/api/**", async (route: Route) => {
    const { pathname } = new URL(route.request().url());
    const body = bodyFor(pathname);

    if (body === undefined) {
      // An empty 200 rather than a 404: an unmocked endpoint should leave the
      // page rendering, so the failure that surfaces is the missing fixture in
      // the diff and not a cascade of error banners.
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}
