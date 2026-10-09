import { isRecord } from './search-contract'

export const ACTIVE_OPTIONS_KEY = 'scraplink-active-jobs-options'
export interface ActiveOptions { max_results: number; watch_mode: boolean; watch_delay_seconds: number }
export const defaultActiveOptions: ActiveOptions = { max_results: 50, watch_mode: true, watch_delay_seconds: 2 }
export function readActiveOptions(): ActiveOptions {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(ACTIVE_OPTIONS_KEY) || 'null')
    if (isRecord(value) && Number.isInteger(value.max_results) && Number(value.max_results) >= 1 && Number(value.max_results) <= 500 &&
      typeof value.watch_mode === 'boolean' && typeof value.watch_delay_seconds === 'number' && value.watch_delay_seconds >= 1.5 && value.watch_delay_seconds <= 3) {
      return value as unknown as ActiveOptions
    }
  } catch { /* Private browsing/storage limits: use safe defaults. */ }
  return { ...defaultActiveOptions }
}

