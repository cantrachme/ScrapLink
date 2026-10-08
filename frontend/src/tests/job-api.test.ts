import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getJobById, getSearchResults } from '../lib/api'
import { job, JOB_ID } from './job-fixtures'
import { json, SEARCH_ID, summary } from './search-fixtures'

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
describe('persisted job response validation', () => {
  it('validates UUIDs before requests', async () => {
    await expect(getJobById('bad')).rejects.toThrow('Invalid job ID')
    await expect(getSearchResults('bad')).rejects.toThrow('Invalid search ID')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('accepts the full search response, preserving nulls and database IDs', async () => {
    const response = { ...summary, jobs: [job] }
    vi.mocked(fetch).mockResolvedValue(json(response))
    expect(await getSearchResults(SEARCH_ID)).toEqual(response)
  })
  it.each([{ id: undefined }, { title: '' }, { source: 'fake' }, { skills: 'Python' }, { compensation: { min_amount: '500' } }, { employment_type: 'made-up' }])('rejects malformed persisted job data %j', async (fields) => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(json({ ...job, ...fields })))
    await expect(getJobById(JOB_ID)).rejects.toThrow('malformed job fields')
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(json({ ...summary, jobs: [{ ...job, ...fields }] })))
    await expect(getSearchResults(SEARCH_ID)).rejects.toThrow('malformed job results')
  })
  it.each([{ search_id: JOB_ID }, { jobs: null }, { total_extracted: -1 }, { status: 'fake' }, { failures: [{}] }])('rejects malformed results envelope %j', async (fields) => {
    vi.mocked(fetch).mockResolvedValue(json({ ...summary, ...fields }))
    await expect(getSearchResults(SEARCH_ID)).rejects.toThrow('malformed job results')
  })
})
