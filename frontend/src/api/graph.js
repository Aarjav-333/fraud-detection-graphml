import client from './client'

export async function getGraphStatus() {
  return (await client.get('/api/graph/status')).data
}
export async function runGraphAnalysis() {
  return (await client.post('/api/graph/analyze', null, { timeout: 180000 })).data
}
export async function getGraphMetrics({ sortBy = 'pagerank', limit = 15, inCycleOnly = false } = {}) {
  return (await client.get('/api/graph/metrics', {
    params: { sort_by: sortBy, limit, in_cycle_only: inCycleOnly },
  })).data
}
export async function getNeighborhood(uid, hops = 1) {
  return (await client.get(`/api/graph/neighborhood/${uid}`, { params: { hops } })).data
}
