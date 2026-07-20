import client from './client'

export async function getFeaturesStatus() {
  return (await client.get('/api/features/status')).data
}
export async function buildFeatures() {
  return (await client.post('/api/features/build', null, { timeout: 120000 })).data
}
export async function previewFeatures({ limit = 12, fraudOnly = false } = {}) {
  return (await client.get('/api/features/preview', { params: { limit, fraud_only: fraudOnly } })).data
}
