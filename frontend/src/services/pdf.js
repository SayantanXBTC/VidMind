/**
 * Export a brief as a PDF, built in the browser with jsPDF (loaded only when
 * someone exports, so it doesn't weigh down the page).
 */
import { formatDuration, formatTimestamp } from '../utils/format.js'

const PAGE = { w: 595.28, h: 841.89 } // A4 in points
const M = 56 // page margin
const WIDTH = PAGE.w - M * 2
const INK = [20, 20, 30]
const MUTED = [110, 110, 125]
const ACCENT = [110, 82, 230]
const TINT = [244, 241, 255]

// jsPDF's built-in fonts only cover Western European characters.
const REPLACEMENTS = { '‑': '-', '−': '-', ' ': ' ', ' ': ' ', ' ': ' ', '→': '->', '←': '<-' }
function clean(text) {
  return String(text || '')
    .replace(/[‑−   →←]/g, (c) => REPLACEMENTS[c])
    .replace(/[^\x09\x0A\x0D\x20-\x7E -ÿ–—‘’“”•…€]/g, '')
}

function fileName(title) {
  const base = clean(title).replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 60)
  return `${base || 'vidmind-brief'}.pdf`
}

export async function buildBriefPdf({ video, result }) {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  let y = M

  const ensure = (height) => {
    if (y + height > PAGE.h - M) {
      doc.addPage()
      y = M
    }
  }

  const paragraph = (text, { size = 11, color = INK, font = 'normal', lineHeight = 1.5, indent = 0, after = 10 } = {}) => {
    doc.setFont('helvetica', font)
    doc.setFontSize(size)
    doc.setTextColor(...color)
    const lines = doc.splitTextToSize(clean(text), WIDTH - indent)
    const step = size * lineHeight
    for (const line of lines) {
      ensure(step)
      doc.text(line, M + indent, y + size)
      y += step
    }
    y += after
  }

  const heading = (text) => {
    ensure(48)
    y += 10
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(9)
    doc.setTextColor(...ACCENT)
    doc.text(clean(text).toUpperCase(), M, y + 9, { charSpace: 1.2 })
    y += 22
  }

  // Brand line
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(9)
  doc.setTextColor(...ACCENT)
  doc.text('VIDMIND  ·  VIDEO BRIEF', M, y + 9, { charSpace: 1.2 })
  y += 28

  // Title
  paragraph(video?.title || 'Video brief', { size: 22, font: 'bold', lineHeight: 1.25, after: 6 })

  // Meta line
  const meta = [
    video?.source === 'upload' ? 'Uploaded video' : 'YouTube',
    formatDuration(video?.duration),
    new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }),
  ].filter(Boolean)
  paragraph(meta.join('  ·  '), { size: 9.5, color: MUTED, after: 4 })
  if (video?.url) {
    doc.setFontSize(9.5)
    doc.setTextColor(...ACCENT)
    doc.textWithLink(clean(video.url), M, y + 9.5, { url: video.url })
    y += 18
  }
  y += 14

  // TL;DR box
  if (result.tldr) {
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(13)
    const lines = doc.splitTextToSize(clean(result.tldr), WIDTH - 36)
    const boxH = 34 + lines.length * 13 * 1.45
    ensure(boxH + 10)
    doc.setFillColor(...TINT)
    doc.roundedRect(M, y, WIDTH, boxH, 10, 10, 'F')
    doc.setFillColor(...ACCENT)
    doc.rect(M, y + 10, 3, boxH - 20, 'F')
    doc.setFontSize(8.5)
    doc.setTextColor(...ACCENT)
    doc.text('TL;DR', M + 18, y + 20, { charSpace: 1.2 })
    doc.setFontSize(13)
    doc.setTextColor(...INK)
    lines.forEach((line, i) => doc.text(line, M + 18, y + 38 + i * 13 * 1.45))
    y += boxH + 18
  }

  heading('Summary')
  result.summary
    .split(/\n\s*\n/)
    .filter(Boolean)
    .forEach((para) => paragraph(para, { size: 11, after: 8 }))

  if (result.key_points?.length) {
    heading('Key points')
    result.key_points.forEach((point, i) => {
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(10)
      doc.setTextColor(...ACCENT)
      ensure(16)
      doc.text(String(i + 1).padStart(2, '0'), M, y + 11)
      paragraph(point, { size: 11, indent: 26, after: 6 })
    })
  }

  if (result.chapters?.length) {
    heading('Chapters')
    result.chapters.forEach((chapter) => {
      ensure(30)
      doc.setFont('courier', 'bold')
      doc.setFontSize(10)
      doc.setTextColor(...ACCENT)
      doc.text(formatTimestamp(chapter.start), M, y + 11)
      paragraph(chapter.title, { size: 11, font: 'bold', indent: 58, after: 1 })
      if (chapter.summary) paragraph(chapter.summary, { size: 10, color: MUTED, indent: 58, after: 8 })
      else y += 6
    })
  }

  // Footer on every page
  const pages = doc.getNumberOfPages()
  for (let i = 1; i <= pages; i += 1) {
    doc.setPage(i)
    doc.setDrawColor(230, 228, 240)
    doc.line(M, PAGE.h - 40, PAGE.w - M, PAGE.h - 40)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(8.5)
    doc.setTextColor(...MUTED)
    doc.text('Generated with VidMind', M, PAGE.h - 26)
    doc.text(`${i} / ${pages}`, PAGE.w - M, PAGE.h - 26, { align: 'right' })
  }
  return doc
}

/** Build the PDF and download it. */
export async function exportBriefPdf({ video, result }) {
  const doc = await buildBriefPdf({ video, result })
  doc.save(fileName(video?.title))
}
