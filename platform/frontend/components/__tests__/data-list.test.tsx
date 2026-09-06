/** `DataList` — the one component that renders a list as both a table and a
 * card stack.
 *
 * The point of these tests is the property that made it one component instead
 * of two: a column declared once appears in both shapes. A `<Table>`/`<CardList>`
 * pair would pass a test per shape and still let the phone view fall behind,
 * because nobody adds the column twice.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DataList, { type Column } from "@/components/ui/data-list";

interface Row {
  id: string;
  name: string;
  mrn: string;
  note: string;
}

const ROWS: Row[] = [
  { id: "1", name: "Ana Ruiz", mrn: "MRN-1", note: "long clinical note" },
  { id: "2", name: "Beto Díaz", mrn: "MRN-2", note: "another note" },
];

const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Paciente", primary: true, render: (r) => r.name },
  { key: "mrn", header: "Historia", render: (r) => r.mrn },
  { key: "note", header: "Notas", desktopOnly: true, render: (r) => r.note },
];

function renderList(props: Partial<React.ComponentProps<typeof DataList<Row>>> = {}) {
  return render(
    <DataList
      items={ROWS}
      columns={COLUMNS}
      rowKey={(r) => r.id}
      loadingLabel="Cargando"
      emptyLabel="Sin resultados"
      caption="Pacientes"
      {...props}
    />,
  );
}

describe("DataList", () => {
  it("AC-017-09 — renders every column in the table shape", () => {
    renderList();
    const table = screen.getByRole("table");

    for (const header of ["Paciente", "Historia", "Notas"]) {
      expect(within(table).getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    expect(within(table).getByText("Ana Ruiz")).toBeInTheDocument();
    expect(within(table).getByText("long clinical note")).toBeInTheDocument();
  });

  it("AC-017-09 — renders the same rows in the card shape, without the desktop-only columns", () => {
    const { container } = renderList();
    const cards = container.querySelector("ul")!;

    // Same data, one row per item.
    expect(within(cards).getByText("Ana Ruiz")).toBeInTheDocument();
    expect(within(cards).getByText("MRN-1")).toBeInTheDocument();
    expect(within(cards).getAllByRole("listitem")).toHaveLength(2);

    // desktopOnly is dropped rather than squeezed in.
    expect(within(cards).queryByText("long clinical note")).toBeNull();
  });

  it("AC-017-10 — labels every non-primary value on the card, so a bare value is never orphaned", () => {
    const { container } = renderList();
    const cards = container.querySelector("ul")!;

    expect(within(cards).getAllByText("Historia").length).toBe(ROWS.length);
  });

  it("makes the whole card tappable when a row href is given", () => {
    const { container } = renderList({ onRowHref: (r) => `/patients/${r.id}` });
    const cards = container.querySelector("ul")!;

    const link = within(cards).getAllByRole("link")[0];
    expect(link).toHaveAttribute("href", "/patients/1");
  });

  it("AC-017-11 — shows a busy placeholder while loading, and no table", () => {
    renderList({ isLoading: true });

    expect(screen.getByLabelText("Cargando")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("AC-017-11 — shows the empty message instead of an empty table", () => {
    renderList({ items: [] });

    expect(screen.getByRole("status")).toHaveTextContent("Sin resultados");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("falls back to the first column as the card headline when none is marked primary", () => {
    const { container } = renderList({
      columns: COLUMNS.map((c) => ({ ...c, primary: false })),
    });
    const firstCard = within(container.querySelector("ul")!).getAllByRole("listitem")[0];

    // "Ana Ruiz" is the headline, so it is NOT repeated as a labelled line.
    expect(within(firstCard).getByText("Ana Ruiz")).toBeInTheDocument();
    expect(within(firstCard).queryByText("Paciente")).toBeNull();
  });
});
