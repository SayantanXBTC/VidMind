import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import Dashboard from './pages/Dashboard.jsx'
import VideoDetails from './pages/VideoDetails.jsx'

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-5 text-center">
      <p className="font-mono text-sm text-accent">404</p>
      <p className="mt-3 font-display text-4xl text-neutral-50">This page doesn't exist</p>
      <Link to="/" className="btn-primary mt-8">
        Go to VidMind
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/videos/:videoId" element={<VideoDetails />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
