import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { getVideoFileUrl } from '../services/api.js'

/**
 * Video player for both sources, exposing seekTo(seconds) and reporting the
 * current time. YouTube is driven through the embed's postMessage API, so
 * chapters and sources seek inside the page instead of opening a new tab.
 */
const Player = forwardRef(function Player({ video, accessToken, onTimeUpdate }, ref) {
  const videoRef = useRef(null)
  const iframeRef = useRef(null)
  const isYoutube = video.source_type === 'youtube'

  const postToYoutube = (message) => {
    iframeRef.current?.contentWindow?.postMessage(JSON.stringify(message), '*')
  }

  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      if (isYoutube) {
        postToYoutube({ event: 'command', func: 'seekTo', args: [seconds, true] })
        postToYoutube({ event: 'command', func: 'playVideo', args: [] })
      } else if (videoRef.current) {
        videoRef.current.currentTime = seconds
        videoRef.current.play().catch(() => {})
      }
    },
  }))

  useEffect(() => {
    if (!isYoutube) return undefined
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
  }, [isYoutube, onTimeUpdate])

  if (isYoutube) {
    const origin = encodeURIComponent(window.location.origin)
    return (
      <iframe
        ref={iframeRef}
        title={video.source_title || 'YouTube video'}
        src={`https://www.youtube.com/embed/${video.youtube_video_id}?enablejsapi=1&rel=0&modestbranding=1&origin=${origin}`}
        className="aspect-video w-full"
        onLoad={() => postToYoutube({ event: 'listening', id: 1, channel: 'widget' })}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    )
  }

  return (
    <video
      ref={videoRef}
      controls
      src={getVideoFileUrl(video.id, accessToken)}
      onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
      className="aspect-video w-full bg-black"
    />
  )
})

export default Player
