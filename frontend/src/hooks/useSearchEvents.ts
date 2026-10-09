import { useEffect, useReducer } from 'react'
import { API_PATHS, getJobSearch } from '../lib/api'
import { isTerminal } from '../lib/search-contract'
import { parseSearchEvent, SEARCH_EVENT_NAMES } from '../lib/search-events'
import type { SearchEvent } from '../types/event'
import type { SearchTask, TaskStatus } from '../types/search'

export type StreamConnection = 'connecting' | 'live' | 'reconnecting' | 'closed' | 'unavailable'
interface Progress {
  status: TaskStatus
  error: string | null
  connection: StreamConnection
  discovered: number
  extracted: number
  failed: number
  pages: number | null
  events: SearchEvent[]
  warning: string | null
}
type TaskState = Pick<SearchTask, 'status' | 'error'>
type Action = { type: 'reset'; task: TaskState } | { type: 'connection'; connection: StreamConnection } |
  { type: 'event'; event: SearchEvent } | { type: 'warning' } | { type: 'snapshot'; task: SearchTask }
const initial = (task: TaskState): Progress => ({ status: task.status, error: task.error,
  connection: isTerminal(task.status) ? 'closed' : 'connecting', discovered: 0, extracted: 0,
  failed: 0, pages: null, events: [], warning: null })

function reduce(state: Progress, action: Action): Progress {
  if (action.type === 'reset') return initial(action.task)
  if (action.type === 'connection') return { ...state, connection: action.connection }
  if (action.type === 'warning') return { ...state, warning: 'An invalid progress event was ignored. Some progress may be unavailable until final results are loaded.' }
  if (action.type === 'snapshot') return { ...state, status: action.task.status, error: action.task.error, connection: 'closed' }
  const e = action.event
  const next = { ...state, events: [...state.events, e].sort((a, b) => Number(a.id) - Number(b.id)).slice(-100) }
  switch (e.event) {
    // Replaying queued history must not regress an already-running snapshot.
    case 'search_queued': break
    case 'search_started': if (!isTerminal(next.status)) next.status = 'running'; break
    case 'page_discovered':
      next.pages = Math.max(next.pages ?? 0, e.data.page_number)
      next.discovered = Math.max(next.discovered, e.data.total_discovered)
      break
    case 'job_saved':
    case 'job_extracted': next.extracted = Math.max(next.extracted, e.data.total_extracted); break
    case 'job_failed': next.failed = Math.max(next.failed, e.data.total_failed); break
    case 'search_completed':
      next.status = 'completed'
      next.connection = 'closed'
      next.discovered = e.data.total_discovered
      next.extracted = e.data.total_extracted
      next.failed = e.data.total_failed
      break
    case 'search_failed': next.status = 'failed'; next.error = e.data.error; next.connection = 'closed'
  }
  return next
}

export function useSearchEvents(task: SearchTask, follow = false) {
  const [state, dispatch] = useReducer(reduce, task, initial)
  const { search_id: searchId, status, error } = task
  useEffect(() => {
    dispatch({ type: 'reset', task: { status, error } })
    if (isTerminal(status) && !follow) return
    if (typeof EventSource === 'undefined') {
      dispatch({ type: 'connection', connection: 'unavailable' })
      return
    }
    const stream = new EventSource(API_PATHS.searchEvents(searchId) + (follow ? '?follow=true' : ''))
    const seen = new Set<string>()
    const controller = new AbortController()
    let closed = false
    let checking = false
    const close = () => { closed = true; stream.close() }
    const onOpen = () => { if (!closed) dispatch({ type: 'connection', connection: 'live' }) }
    const onError = () => {
      if (closed) return
      dispatch({ type: 'connection', connection: stream.readyState === 2 ? 'unavailable' : 'reconnecting' })
      // One reconciliation on disconnection, never a competing reconnect loop.
      // This also closes streams for historical terminal tasks without events.
      if (checking || follow) return
      checking = true
      getJobSearch(searchId, controller.signal).then((latest) => {
        if (!closed && isTerminal(latest.status)) {
          close()
          dispatch({ type: 'snapshot', task: latest })
        }
      }).catch(() => { /* Keep the last known task state while offline. */ })
        .finally(() => { checking = false })
    }
    const listeners = SEARCH_EVENT_NAMES.map((name) => {
      const listener = (message: Event) => {
        if (closed) return
        const event = parseSearchEvent(name, message as MessageEvent, searchId)
        if (!event) { dispatch({ type: 'warning' }); return }
        if (seen.has(event.id)) return
        seen.add(event.id)
        dispatch({ type: 'event', event })
        if (event.event === 'search_completed' || event.event === 'search_failed') {
          if (follow) dispatch({ type: 'connection', connection: 'live' })
          else close()
        }
      }
      stream.addEventListener(name, listener)
      return { name, listener }
    })
    stream.addEventListener('open', onOpen)
    stream.addEventListener('error', onError)
    return () => {
      close()
      controller.abort()
      listeners.forEach(({ name, listener }) => stream.removeEventListener(name, listener))
      stream.removeEventListener('open', onOpen)
      stream.removeEventListener('error', onError)
    }
  }, [searchId, status, error, follow])
  return state
}
