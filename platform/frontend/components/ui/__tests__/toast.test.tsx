import { act, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "@/components/ui/toast";

function Fire({ message }: { message: string }) {
  const show = useToast();
  useEffect(() => show(message), [show, message]);
  return null;
}

describe("toast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("enters, fades out just before it goes, and is gone after four seconds", () => {
    render(
      <ToastProvider>
        <Fire message="Saved" />
      </ToastProvider>,
    );
    const toast = () => screen.getByText("Saved").closest("div")!;
    expect(toast().className).toContain("animate-toast-in");

    act(() => vi.advanceTimersByTime(3899));
    expect(toast().className).toContain("animate-toast-in");

    act(() => vi.advanceTimersByTime(1));
    expect(toast().className).toContain("animate-toast-out");
    expect(toast().className).not.toContain("animate-toast-in");

    act(() => vi.advanceTimersByTime(100));
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });
});
