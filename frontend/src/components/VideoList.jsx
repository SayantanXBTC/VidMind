import VideoCard from './VideoCard.jsx'

export default function VideoList({ entries, onDelete, selecting, selectedIds, onToggleSelect }) {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map((entry, index) => (
        <VideoCard
          key={entry.id}
          entry={entry}
          index={index}
          onDelete={onDelete}
          selecting={selecting}
          selected={selectedIds?.has(entry.id)}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  )
}
