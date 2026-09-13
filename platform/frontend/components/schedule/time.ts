/** Time helpers shared by the week grid and the day agenda.
 *
 * The convention is load-bearing and wrong-looking on purpose: appointment
 * timestamps come back naive, so `new Date(iso + "Z")` parses them as UTC and
 * `getUTC*` reads them back unshifted — the wall-clock time the server meant,
 * with no local-timezone conversion applied.
 *
 * Both views MUST go through here. A `format(new Date(iso))` anywhere else
 * would apply the browser's offset and show the same appointment at two
 * different times depending on which view you were looking at.
 */

export const START_HOUR = 7;
export const END_HOUR = 20;
export const ROW_MINUTES = 30;
export const ROW_HEIGHT_REM = 3;
export const ROWS = ((END_HOUR - START_HOUR) * 60) / ROW_MINUTES;

function asUtc(iso: string): Date {
  return new Date(iso + "Z");
}

/** Minutes from the top of the grid (START_HOUR), for vertical placement. */
export function minutesFromDayStart(iso: string): number {
  const d = asUtc(iso);
  return d.getUTCHours() * 60 + d.getUTCMinutes() - START_HOUR * 60;
}

/** "14:30" — the appointment's own wall-clock time. */
export function slotTime(iso: string): string {
  const d = asUtc(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export function durationMinutes(startIso: string, endIso: string): number {
  return (asUtc(endIso).getTime() - asUtc(startIso).getTime()) / 60000;
}
