import { BrowserRouter } from 'react-router'
import { AppRoutes } from './router'

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
