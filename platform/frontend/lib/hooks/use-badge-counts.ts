"use client";

/** The one poll behind every counter in the chrome.
 *
 * Before this there were two independent 30-second polls — the dashboard
 * bootstrap and `NotificationBell`'s own `useEffect` — and the task badge would
 * have made three, all of them counting rows, all of them running in every open
 * tab. One query, one interval, shared by whoever needs a number.
 *
 * `staleTime` sits just under the interval so a component mounting between
 * ticks reads the cached value instead of firing its own request.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type BadgeCounts } from "@/lib/api";

export const BADGES_QUERY_KEY = ["badges"] as const;

const REFETCH_MS = 30_000;

export function useBadgeCounts() {
  return useQuery<BadgeCounts>({
    queryKey: BADGES_QUERY_KEY,
    queryFn: api.badges,
    refetchInterval: REFETCH_MS,
    staleTime: REFETCH_MS - 5_000,
    // A counter is decoration: a failed poll should leave the last number on
    // screen, not blank the chrome or throw to an error boundary.
    retry: false,
    placeholderData: (previous) => previous,
  });
}

/** Call after any mutation that changes what the badges count. */
export function useInvalidateBadges() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: BADGES_QUERY_KEY });
}
