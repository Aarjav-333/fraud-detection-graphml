import client from './client'

export async function getMLStatus() {
  return (await client.get('/api/ml/status')).data
}
export async function trainModels() {
  return (await client.post('/api/ml/train', null, { timeout: 300000 })).data
}
export async function getTopRisk(limit = 15) {
  return (await client.get('/api/ml/top-risk', { params: { limit } })).data
}
