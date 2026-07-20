import client from './client'

export async function listExports() {
  return (await client.get('/api/reports/exports')).data
}

async function downloadBlob(url, filename) {
  const res = await client.get(url, { responseType: 'blob', timeout: 120000 })
  const blobUrl = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(blobUrl)
}

export async function downloadCsv(name) {
  return downloadBlob(`/api/reports/export/${name}`, `${name}.csv`)
}
export async function downloadSummaryPdf() {
  return downloadBlob('/api/reports/summary-pdf', 'fraud_detection_summary.pdf')
}
