import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

/**
 * Embedded YouTube player exposing seekTo(seconds) and reporting the current
 * time, driven through the embed's postMessage API so chapters and sources
 * seek inside the page instead of opening a new tab.
 */
const Player = forwardRef(function Player({ videoId, title, onTimeUpdate }, ref) {
  const iframeRef = useRef(null)

  const post = (message) => {
    iframeRef.current?.contentWindow?.postMessage(JSON.stringify(message), '*')
  }

  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      post({ event: 'command', func: 'seekTo', args: [seconds, true] })
      post({ event: 'command', func: 'playVideo', args: [] })
    },
  }))

  useEffect(() => {
    const onMessage = (event) => {
      if (!/^https:\/\/www\.youtube(-nocookie)?\.com$/.test(event.origin)) return
      if (event.source !== iframeRef.current?.contentWindow) return
      let data = event.data
      if (typeof data === 'string') {
        try {
          data = JSON.parse(data)
        } catch {
          return
        }
      }
      const time = data?.info?.currentTime
      if (typeof time === 'number') onTimeUpdate?.(time)
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [onTimeUpdate])

  const origin = encodeURIComponent(window.location.origin)
  return (
    <iframe
      ref={iframeRef}
      title={title || 'YouTube video'}
      src={`https://www.youtube.com/embed/${videoId}?enablejsapi=1&rel=0&modestbranding=1&origin=${origin}`}
      className="aspect-video w-full"
      onLoad={() => post({ event: 'listening', id: 1, channel: 'widget' })}
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowFullScreen
    />
  )
})

export default Player
