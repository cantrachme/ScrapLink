import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchEvents } from '../hooks/useSearchEvents'
import { parseSearchEvent, SEARCH_EVENT_NAMES } from '../lib/search-events'
import { completed, extracted, failure, installEventSource, json, MockEventSource, OTHER_ID, page, queued, SEARCH_ID, started, stream, task } from './search-fixtures'

beforeEach(() => { installEventSource(); vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(json(task)))) })

describe('native SSE progress', () => {
  it('connects through the relative endpoint and listens for every named event', () => {
    const { result } = renderHook(() => useSearchEvents(task))
    expect(stream().url).toBe(`/api/v1/jobs/search/${SEARCH_ID}/events`)
    expect(stream().addEventListener.mock.calls.map(([name]) => name)).toEqual(expect.arrayContaining(SEARCH_EVENT_NAMES))
    expect(result.current.connection).toBe('connecting')
    act(() => stream().open())
    expect(result.current.connection).toBe('live')
    expect(result.current.status).toBe('pending')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('handles all progress events using cumulative backend totals', () => {
    const { result } = renderHook(() => useSearchEvents(task))
    act(() => stream().emit('search_queued', queued, 1))
    expect(result.current.status).toBe('pending')
    act(() => stream().emit('search_started', started, 2))
    expect(result.current.status).toBe('running')
    act(() => {
      stream().emit('page_discovered', page, 3)
      stream().emit('job_extracted', extracted, 4)
      stream().emit('job_extracted', { ...extracted, total_extracted: 2 }, 5)
      stream().emit('job_failed', failure, 6)
      stream().emit('page_discovered', { page_number: 2, new_jobs_discovered: 0, total_discovered: 18 }, 7)
    })
    expect(result.current).toMatchObject({ pages: 2, discovered: 18, extracted: 2, failed: 1 })
    act(() => stream().emit('search_completed', { ...completed, total_extracted: 1 }, 8))
    expect(result.current).toMatchObject({ status: 'completed', extracted: 1, connection: 'closed' })
    expect(stream().close).toHaveBeenCalledTimes(1)
    act(() => stream().disconnect())
    expect(fetch).not.toHaveBeenCalled()
  })
  it('uses the actual failure payload and closes immediately', () => {
    const { result } = renderHook(() => useSearchEvents(task))
    act(() => stream().emit('search_failed', { search_id: SEARCH_ID, status: 'failed', error: 'Browser execution failed' }, 2))
    expect(result.current).toMatchObject({ status: 'failed', error: 'Browser execution failed', connection: 'closed' })
    expect(stream().close).toHaveBeenCalledTimes(1)
  })
  it('sorts by sequence, deduplicates replay, and never regresses running status', () => {
    const running = { ...task, status: 'running' as const }
    const { result } = renderHook(() => useSearchEvents(running))
    act(() => {
      stream().emit('job_extracted', { ...extracted, total_extracted: 2 }, 5)
      stream().emit('search_queued', queued, 1)
      stream().emit('page_discovered', page, 3)
      stream().emit('job_extracted', extracted, 4)
      stream().emit('job_extracted', extracted, 4)
    })
    expect(result.current.events.map((event) => event.id)).toEqual(['1', '3', '4', '5'])
    expect(result.current.extracted).toBe(2)
    expect(result.current.status).toBe('running')
  })
  it('leaves reconnection and Last-Event-ID to the same native EventSource', async () => {
    const { result } = renderHook(() => useSearchEvents(task))
    const original = stream()
    act(() => { original.open(); original.emit('page_discovered', page, 3); original.disconnect() })
    expect(result.current.connection).toBe('reconnecting')
    expect(result.current.status).toBe('pending')
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    act(() => { original.open(); original.emit('page_discovered', page, 3) })
    expect(result.current.connection).toBe('live')
    expect(result.current.events).toHaveLength(1)
    expect(result.current.discovered).toBe(18)
    expect(MockEventSource.instances).toHaveLength(1)
    expect(original.close).not.toHaveBeenCalled()
  })
  it('reconciles a stream ending without a terminal event for legacy tasks', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ...task, status: 'completed' }))
    const { result } = renderHook(() => useSearchEvents(task))
    act(() => stream().disconnect())
    await waitFor(() => expect(result.current.status).toBe('completed'))
    expect(stream().close).toHaveBeenCalledTimes(1)
  })
  it.each(['completed', 'failed'] as const)('never opens a stream for an already %s task', (status) => {
    const { result } = renderHook(() => useSearchEvents({ ...task, status }))
    expect(MockEventSource.instances).toHaveLength(0)
    expect(result.current.connection).toBe('closed')
  })
  it('cleans up every listener and closes on unmount', () => {
    const view = renderHook(() => useSearchEvents(task))
    const original = stream()
    view.unmount()
    expect(original.close).toHaveBeenCalledTimes(1)
    expect(original.removeEventListener.mock.calls).toEqual(original.addEventListener.mock.calls)
  })
  it('cleans up and resets on search ID changes, ignoring late old events', () => {
    const { result, rerender } = renderHook(({ current }) => useSearchEvents(current), { initialProps: { current: task } })
    const original = stream()
    act(() => original.emit('page_discovered', page, 3))
    rerender({ current: { ...task, search_id: OTHER_ID } })
    expect(original.close).toHaveBeenCalledTimes(1)
    expect(result.current.discovered).toBe(0)
    expect(result.current.events).toHaveLength(0)
    expect(stream().url).toContain(OTHER_ID)
    act(() => original.emit('job_extracted', extracted, 4))
    expect(result.current.extracted).toBe(0)
  })
  it('ignores malformed JSON, invalid payloads, wrong parent IDs and invalid sequences', () => {
    const { result } = renderHook(() => useSearchEvents(task))
    act(() => {
      stream().dispatchEvent(new MessageEvent('page_discovered', { data: '{', lastEventId: '1' }))
      stream().emit('page_discovered', { ...page, total_discovered: -1 }, 2)
      stream().emit('page_discovered', { ...page, page_number: 1.5 }, 3)
      stream().emit('job_extracted', { ...extracted, title: '<script>' }, 4)
      stream().emit('job_failed', { ...failure, error: 'not in contract' }, 5)
      stream().emit('search_completed', { ...completed, search_id: OTHER_ID }, 6)
      stream().emit('page_discovered', page, '')
      stream().emit('page_discovered', page, 2147483648)
      stream().emit('page_discovered', { ...page, timestamp: 'invented' }, 9)
      stream().dispatchEvent(new MessageEvent('message', { data: ': heartbeat' }))
    })
    expect(result.current.warning).toContain('invalid progress event')
    expect(result.current.events).toHaveLength(0)
    expect(result.current.discovered).toBe(0)
    expect(stream().close).not.toHaveBeenCalled()
    act(() => stream().emit('page_discovered', page, 10))
    expect(result.current.discovered).toBe(18)
  })
  it('caps activity at 100 entries without losing counters or deduplication', () => {
    const { result } = renderHook(() => useSearchEvents(task))
    act(() => {
      stream().emit('page_discovered', page, 1)
      for (let n = 2; n <= 120; n++) stream().emit('job_extracted', { ...extracted, total_extracted: n - 1 }, n)
      stream().emit('page_discovered', page, 1)
    })
    expect(result.current.events).toHaveLength(100)
    expect(result.current.events[0].id).toBe('21')
    expect(result.current.extracted).toBe(119)
    expect(result.current.discovered).toBe(18)
    expect(result.current.pages).toBe(1)
  })
})

it('accepts browser actions but rejects fabricated or arbitrary action names', () => {
  const event = parseSearchEvent('browser_action', new MessageEvent('browser_action', {
    lastEventId: '3', data: JSON.stringify({ action: 'typed_keyword' }),
  }), SEARCH_ID)
  expect(event?.event).toBe('browser_action')
  expect(parseSearchEvent('browser_action', new MessageEvent('browser_action', {
    lastEventId: '4', data: JSON.stringify({ action: 'fake_scraping' }),
  }), SEARCH_ID)).toBeNull()
})
