/** Slow-drifting aurora light behind every page. Purely decorative. */
export default function Background() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink-950">
      <div className="absolute -left-[20%] -top-[30%] h-[70vmax] w-[70vmax] animate-drift rounded-full bg-[radial-gradient(closest-side,rgba(139,108,255,0.28),transparent)] blur-2xl" />
      <div className="absolute -right-[25%] top-[10%] h-[60vmax] w-[60vmax] animate-drift-slow rounded-full bg-[radial-gradient(closest-side,rgba(127,231,255,0.12),transparent)] blur-2xl" />
      <div className="absolute bottom-[-35%] left-[20%] h-[65vmax] w-[65vmax] animate-drift rounded-full bg-[radial-gradient(closest-side,rgba(242,210,155,0.10),transparent)] blur-2xl [animation-delay:-11s]" />
      <div className="bg-grid absolute inset-0" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(5,5,10,0.85))]" />
    </div>
  )
}
