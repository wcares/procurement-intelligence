/** Local date and time of an ISO timestamp, and how long ago or ahead it is. */
export const when = (iso: string) => new Date(iso).toLocaleString();

export function relative(iso: string, now = Date.now()): string {
  const min = Math.round((new Date(iso).getTime() - now) / 60000);
  const abs = Math.abs(min);
  const text = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} days`;
  return min >= 0 ? `in ${text}` : `${text} ago`;
}
