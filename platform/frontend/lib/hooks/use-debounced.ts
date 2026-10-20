import { useEffect, useState } from "react";

/** `value`, but only after it has held still for `ms`. Compared by content, so a
 * caller can build a fresh object each render without restarting the wait. */
export function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  const key = JSON.stringify(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(JSON.parse(key) as T), ms);
    return () => clearTimeout(id);
    // `key` stands for `value`: see above.
  }, [key, ms]);
  return settled;
}
