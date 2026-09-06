/** The agenda card on the work center.
 *
 * `/api/dashboard/bootstrap` has always returned `agenda`. The old dashboard
 * fetched it and rendered none of it, so "who am I seeing next" — the first
 * question of the day — was a second page. These tests hold the card to the
 * two things that makes it worth the space: it says when the next appointment
 * is, and it never claims there are none when there are.
 *
 * Verifies AC-019-03, AC-019-04 (docs/specs/SPEC-019-work-center.md).
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgendaTodayCard from "@/components/work/agenda-today-card";
import type { TodayAgenda } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const NOW = new Date("2026-09-06T09:00:00Z");

function agenda(overrides: Partial<TodayAgenda> = {}): TodayAgenda {
  return {
    date: "2026-09-06",
    count: 2,
    next_at: "2026-09-06T09:20:00Z",
    items: [
      {
        id: "A1",
        start_at: "2026-09-06T09:20:00Z",
        end_at: "2026-09-06T09:40:00Z",
        patient_name: "Ana Ruiz",
        reason: "Control",
      },
      {
        id: "A2",
        start_at: "2026-09-06T10:00:00Z",
        end_at: "2026-09-06T10:20:00Z",
        patient_name: "Beto Díaz",
        reason: "",
      },
    ],
    ...overrides,
  };
}

function renderCard(value?: TodayAgenda) {
  return render(
    <LanguageProvider>
      <AgendaTodayCard agenda={value} />
    </LanguageProvider>,
  );
}

describe("AgendaTodayCard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("AC-019-03 — renders the agenda the dashboard used to throw away", () => {
    renderCard(agenda());

    expect(screen.getByText("Ana Ruiz")).toBeInTheDocument();
    expect(screen.getByText("Beto Díaz")).toBeInTheDocument();
  });

  it("AC-019-04 — counts down to the next appointment in minutes", () => {
    renderCard(agenda());

    // Interpolated through t(key, vars) rather than a hand-rolled .replace().
    expect(screen.getByText(/20 min/)).toBeInTheDocument();
  });

  it("switches to a clock time once the next appointment is over an hour away", () => {
    renderCard(agenda({ next_at: "2026-09-06T14:00:00Z" }));

    expect(screen.queryByText(/min/)).toBeNull();
  });

  it("says an appointment is under way rather than counting backwards", () => {
    renderCard(agenda({ next_at: "2026-09-06T08:50:00Z" }));

    // A negative countdown ("in -10 min") is worse than no countdown.
    expect(screen.queryByText(/-\d+ min/)).toBeNull();
  });

  it("shows an empty state, and no rows, when the day is clear", () => {
    renderCard(agenda({ count: 0, items: [], next_at: null }));

    expect(screen.getByText(/no appointments today/i)).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  it("caps the rows and says how many more there are", () => {
    const many = agenda({
      count: 9,
      items: Array.from({ length: 9 }, (_, i) => ({
        id: `A${i}`,
        start_at: "2026-09-06T11:00:00Z",
        end_at: "2026-09-06T11:20:00Z",
        patient_name: `Paciente ${i}`,
        reason: "",
      })),
    });
    renderCard(many);

    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByText(/5 more/)).toBeInTheDocument();
  });

  it("renders nothing alarming when the payload is missing entirely", () => {
    renderCard(undefined);

    expect(screen.getByText(/no appointments today/i)).toBeInTheDocument();
  });
});
