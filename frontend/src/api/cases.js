import client from './client'

export async function getCasesSummary() {
  return (await client.get('/api/cases/summary')).data
}
export async function listCases({ skip = 0, limit = 25, status = '', q = '' } = {}) {
  return (await client.get('/api/cases', {
    params: { skip, limit, status: status || undefined, q: q || undefined },
  })).data
}
export async function getCase(uid) {
  return (await client.get(`/api/cases/${uid}`)).data
}
export async function createCase(body) {
  return (await client.post('/api/cases', body)).data
}
export async function updateCase(uid, body) {
  return (await client.put(`/api/cases/${uid}`, body)).data
}
export async function deleteCase(uid) {
  return (await client.delete(`/api/cases/${uid}`)).data
}
