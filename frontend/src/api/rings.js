import client from './client'

export async function getRingsStatus() {
  return (await client.get('/api/rings/status')).data
}
export async function detectRings() {
  return (await client.post('/api/rings/detect', null, { timeout: 180000 })).data
}
export async function getRing(ringId) {
  return (await client.get(`/api/rings/${ringId}`)).data
}
