import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { AuthProvider, useAuth } from './auth/AuthProvider.jsx'
import Dashboard from './pages/Dashboard.jsx'
import VideoDetails from './pages/VideoDetails.jsx'
import Login from './pages/Login.jsx'

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-5 text-center">
      <p className="font-mono text-sm text-accent">404</p>
      <p className="mt-3 font-display text-4xl text-neutral-50">This page doesn't exist</p>
      <Link to="/" className="btn-primary mt-8">
        Go to your library
      </Link>
    </div>
  )
}

function AppRoutes() {
  const { loading, signedIn } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/10 border-t-accent" />
      </div>
    )
  }

  // Signed-out visitors see the sign-in screen at any URL; after signing in
  // they land back on the page they asked for.
  if (!signedIn) return <Login />

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/videos/:videoId" element={<VideoDetails />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
