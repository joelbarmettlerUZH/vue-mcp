/** `days` query parameter: an integer from 1 to 365, default 30. Null when invalid. */
export function parseDays(raw: string | null): number | null {
  if (raw === null) return 30;
  if (!/^\d{1,3}$/.test(raw)) return null;
  const days = Number(raw);
  return days >= 1 && days <= 365 ? days : null;
}
