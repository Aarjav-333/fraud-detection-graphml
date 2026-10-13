// Shared display formatting.

export const money = (n) => (n == null ? '—' : '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 }))
export const pct = (v, digits = 1) => (v == null ? '—' : (v * 100).toFixed(digits) + '%')

// Times the backend records itself (reviews, notifications, emails) are UTC
// without a zone suffix: show them in the viewer's local time.
export function eventTime(iso) {
  if (!iso) return '—'
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

// Transaction timestamps, shown the same way as on the Transactions page.
export function txnTime(iso) {
  return iso ? new Date(iso).toLocaleString('en-IN') : '—'
}
