import { useEffect } from 'react'

export default function ConfirmDialog({
  title,
  description,
  confirmLabel = 'Confirm',
  onConfirm,
  onCancel,
}) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onCancel])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="card w-full max-w-sm animate-fade-up p-7"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="font-display text-2xl text-neutral-50">
          {title}
        </h2>
        {description && <p className="mt-2 text-sm leading-relaxed text-neutral-400">{description}</p>}
        <div className="mt-7 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="btn-ghost">
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            autoFocus
            className="btn bg-rose-500 text-white hover:bg-rose-400 focus-visible:ring-rose-400/60"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
