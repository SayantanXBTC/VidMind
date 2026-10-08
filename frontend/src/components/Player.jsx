import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { fileUrl, rememberFile } from '../services/localFiles.js'
import { FileVideo } from './Icons.jsx'
import { UploadCover } from './VideoCard.jsx'

/**
 * Video player exposing seekTo(seconds) and reporting the current time.
 *  - YouTube: the embed, driven through its postMessage API.
 *  - Uploads: the server never keeps the file, so it plays from the visitor's
 *    computer — automatically right after uploading, or after they pick it.
 */
const Player = forwardRef(function Player({ videoId, source = 'youtube', title, onTimeUpdate }, ref) {
  const iframeRef = useRef(null)
  const videoRef = useRef(null)
  const pickerRef = useRef(null)
  const [localUrl, setLocalUrl] = useState(() => (source === 'upload' ? fileUrl(videoId) : null))

  const post = (message) => iframeRef.current?.contentWindow?.postMessage(JSON.stringify(message), '*')

  useImperativeHandle(ref, () => ({
    seekTo(seconds) {
      if (source === 'upload') {
        if (videoRef.current) {
          videoRef.current.currentTime = seconds
          videoRef.current.play().catch(() => {})
        }
        return
      }
      post({ event: 'command', func: 'seekTo', args: [seconds, true] })
      post({ event: 'command', func: 'playVideo', args: [] })
    },
  }))

  useEffect(() => {
    if (source !== 'youtube') return undefined
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
  }, [source, onTimeUpdate])

  if (source === 'upload') {
    if (localUrl) {
      return (
        <video
          ref={videoRef}
          src={localUrl}
          controls
          playsInline
          onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
          className="aspect-video w-full bg-black"
        />
      )
    }
    return (
      <div className="relative aspect-video w-full">
        <UploadCover id={videoId} title={title} className="absolute inset-0 opacity-60" />
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink-950/50 p-6 text-center backdrop-blur-[2px]">
          <FileVideo className="h-7 w-7 text-white/80" />
          <p className="text-sm text-neutral-200">Your video stays on your computer.</p>
          <button type="button" onClick={() => pickerRef.current?.click()} className="btn-primary py-2 text-xs">
            Choose the file to play it here
          </button>
          <input
            ref={pickerRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) setLocalUrl(rememberFile(videoId, file))
            }}
          />
        </div>
      </div>
    )
  }

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
