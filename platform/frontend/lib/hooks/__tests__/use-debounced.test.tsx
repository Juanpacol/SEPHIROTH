import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDebounced } from "@/lib/hooks/use-debounced";

describe("useDebounced", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("holds the old value until the new one has held still", () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 300), {
      initialProps: { v: "a" },
    });
    rerender({ v: "b" });
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe("a");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe("b");
  });

  it("restarts the wait on every change", () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 300), {
      initialProps: { v: 1 },
    });
    rerender({ v: 2 });
    act(() => vi.advanceTimersByTime(200));
    rerender({ v: 3 });
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe(1);
    act(() => vi.advanceTimersByTime(100));
    expect(result.current).toBe(3);
  });

  it("does not restart for an equal object built afresh each render", () => {
    const { result, rerender } = renderHook(({ n }) => useDebounced({ n }, 300), { initialProps: { n: 1 } });
    rerender({ n: 2 });
    act(() => vi.advanceTimersByTime(200));
    rerender({ n: 2 });
    act(() => vi.advanceTimersByTime(100));
    expect(result.current).toEqual({ n: 2 });
  });
});
