import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DataList, { type Column } from "@/components/ui/data-list";

interface Row {
  id: string;
  name: string;
}

const ITEMS: Row[] = [
  { id: "p1", name: "Ada Lovelace" },
  { id: "p2", name: "Alan Turing" },
];

const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Name", render: (row) => row.name, primary: true },
  { key: "id", header: "Id", render: (row) => row.id },
];

function renderList(props: Partial<Parameters<typeof DataList<Row>>[0]> = {}) {
  return render(
    <DataList<Row>
      items={ITEMS}
      columns={COLUMNS}
      rowKey={(row) => row.id}
      loadingLabel="Loading…"
      emptyLabel="No items."
      caption="Rows"
      {...props}
    />
  );
}

describe("DataList", () => {
  it("links every table row when onRowHref is given", () => {
    renderList({ onRowHref: (row) => `/patients/${row.id}` });
    const links = within(screen.getByRole("table")).getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/patients/p1");
  });

  it("names the link after the first column's text", () => {
    renderList({ onRowHref: (row) => `/patients/${row.id}` });
    expect(
      within(screen.getByRole("table")).getByRole("link", { name: /Ada Lovelace/ })
    ).toBeInTheDocument();
  });

  it("renders no links in the table when onRowHref is omitted", () => {
    renderList();
    expect(within(screen.getByRole("table")).queryAllByRole("link")).toEqual([]);
  });

  it("still links the card shape (regression)", () => {
    renderList({ onRowHref: (row) => `/patients/${row.id}` });
    const links = within(screen.getByRole("list")).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/patients/p1");
  });

  it("renders neither shape while loading, and the empty label when there are no items", () => {
    const { unmount } = renderList({ isLoading: true });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    unmount();

    renderList({ items: [] });
    expect(screen.getByRole("status")).toHaveTextContent("No items.");
  });
});
