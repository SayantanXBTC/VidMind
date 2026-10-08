import VideoCard from './VideoCard.jsx'

export default function VideoList({ videos, onDelete, onRetried, selecting, selectedIds, onToggleSelect }) {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {videos.map((video, index) => (
        <VideoCard
          key={video.id}
          video={video}
          index={index}
          onDelete={onDelete}
          onRetried={onRetried}
          selecting={selecting}
          selected={selectedIds?.has(video.id)}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  )
}
