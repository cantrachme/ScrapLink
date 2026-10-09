import { Route, Routes } from 'react-router'
import { AppLayout } from '../components/layout/AppLayout'
import { DashboardPage } from '../pages/DashboardPage'
import { SearchPage } from '../pages/SearchPage'
import { SearchDetailsPage } from '../pages/SearchDetailsPage'
import { JobDetailsPage } from '../pages/JobDetailsPage'
import { ActiveJobsPage } from '../pages/ActiveJobsPage'
import { NotFoundPage } from '../pages/NotFoundPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="active-jobs" element={<ActiveJobsPage />} />
        <Route path="active-jobs/:searchId" element={<ActiveJobsPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="searches/:searchId" element={<SearchDetailsPage />} />
        <Route path="jobs/:jobId" element={<JobDetailsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
