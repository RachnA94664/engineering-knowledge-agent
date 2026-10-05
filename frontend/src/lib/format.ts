/** Turn backend values into readable text. */

export function formatTime(value: string | null | undefined): string {
  if (!value) return '–'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '–'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

/** "not_run" -> "not run" */
export function humanize(value: string): string {
  return value.replace(/_/g, ' ')
}

export const ACTOR_MAX_LENGTH = 64
export const MESSAGE_MAX_LENGTH = 1000
