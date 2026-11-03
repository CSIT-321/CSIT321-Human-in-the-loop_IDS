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
