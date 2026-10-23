/** "María Fernanda Restrepo Villegas" → "MV": the first and last name, never the whole name, so the
 * letters fit the circle they sit in. A title ("Dr.") is dropped. */
export function initialsOf(name: string): string {
  const words = name.split(/\s+/).filter((w) => w && !/^(dr|dra|sr|sra)\.?$/i.test(w));
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}
