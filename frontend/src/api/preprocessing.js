import client from './client'

export async function getReport() {
  return (await client.get('/api/preprocessing/report')).data
}
export async function runClean() {
  return (await client.post('/api/preprocessing/clean')).data
}
