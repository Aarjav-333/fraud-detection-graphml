import client from './client'

export async function generateAlerts(mlThreshold = 0.8) {
  return (await client.post('/api/alerts/generate', { ml_threshold: mlThreshold }, { timeout: 120000 })).data
}
export async function getAlertsSummary() {
  return (await client.get('/api/alerts/summary')).data
}
export async function listAlerts({ skip = 0, limit = 25, status = '', risk = '', q = '' } = {}) {
  return (await client.get('/api/alerts', {
    params: { skip, limit, status: status || undefined, risk: risk || undefined, q: q || undefined },
  })).data
}
export async function updateAlertStatus(uid, status) {
  return (await client.put(`/api/alerts/${uid}/status`, { status })).data
}
