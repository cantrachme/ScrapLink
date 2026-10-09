import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { AssistedJobForm } from '../components/jobs/AssistedJobForm'
import { json, task } from './search-fixtures'

it('saves only user-entered title and URL and refreshes results', async () => {
  const onSaved = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ id: 'saved' })))
  render(<AssistedJobForm task={{ ...task, status: 'completed' }} onSaved={onSaved} />)
  fireEvent.change(screen.getByLabelText('Job title to save'), { target: { value: 'DevOps Engineer' } })
  fireEvent.change(screen.getByLabelText('Original job URL'), { target: { value: 'https://www.linkedin.com/jobs/view/123/' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save job' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Job saved')
  expect(onSaved).toHaveBeenCalledOnce()
  expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({
    title: 'DevOps Engineer', job_url: 'https://www.linkedin.com/jobs/view/123/', location: null,
    workplace_type: null, description: null,
  })
})
