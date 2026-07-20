import client from './client'

export async function listAccounts({ skip = 0, limit = 25, q = '', activeOnly = false } = {}) {
  const res = await client.get('/api/accounts', {
    params: { skip, limit, q: q || undefined, active_only: activeOnly },
  })
  return res.data
}
export async function createAccount(data) {
  return (await client.post('/api/accounts', data)).data
}
export async function updateAccount(uid, data) {
  return (await client.put(`/api/accounts/${uid}`, data)).data
}
export async function deactivateAccount(uid) {
  return (await client.post(`/api/accounts/${uid}/deactivate`)).data
}
export async function activateAccount(uid) {
  return (await client.post(`/api/accounts/${uid}/activate`)).data
}
