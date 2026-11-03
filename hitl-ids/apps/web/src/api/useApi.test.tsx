import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { useApi } from "./useApi";

it("keeps successful workspace data visible during a background refresh", async () => {
  let finishRefresh: ((value: number) => void) | undefined;
  const load = vi.fn()
    .mockResolvedValueOnce(50)
    .mockImplementationOnce(() => new Promise<number>(resolve => { finishRefresh = resolve; }));
  const { result } = renderHook(() => useApi(load, [], { keepPreviousData: true }));
  await waitFor(() => expect(result.current.status).toBe("success"));
  act(() => result.current.reload());
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(result.current).toMatchObject({ status: "success", data: 50 });
  await act(async () => finishRefresh?.(51));
  expect(result.current).toMatchObject({ status: "success", data: 51 });
});

it("clears old query rows when the filter changes", async () => {
  const { result, rerender } = renderHook(({ filter }) => useApi(async () => filter, [filter],
    { keepPreviousData: true }), { initialProps: { filter: "all" } });
  await waitFor(() => expect(result.current).toMatchObject({ status: "success", data: "all" }));
  rerender({ filter: "critical" });
  await waitFor(() => expect(result.current).toMatchObject({ status: "success", data: "critical" }));
});

it("preserves visible rows when a background reconciliation fails", async () => {
  const load = vi.fn().mockResolvedValueOnce(7).mockRejectedValueOnce(new Error("temporary outage"));
  const { result } = renderHook(() => useApi(load, [], { keepPreviousData: true }));
  await waitFor(() => expect(result.current).toMatchObject({ status: "success", data: 7 }));
  act(() => result.current.reload());
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(result.current).toMatchObject({ status: "success", data: 7 });
});
