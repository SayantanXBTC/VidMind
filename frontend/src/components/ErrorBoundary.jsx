import { Component } from 'react'

/** Last line of defence: a render crash shows a recovery screen, not a blank page. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('VidMind crashed while rendering', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-5 text-center">
        <p className="font-display text-4xl text-neutral-50">Something broke on this page</p>
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-neutral-400">
          Your videos are safe. Reload the page, or go back to your library.
        </p>
        <div className="mt-8 flex gap-2">
          <button type="button" onClick={() => window.location.reload()} className="btn-primary">
            Reload
          </button>
          <a href="/" className="btn-ghost">
            Library
          </a>
        </div>
      </div>
    )
  }
}
