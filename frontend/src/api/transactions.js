import client from './client'

export async function listTransactions({ skip = 0, limit = 25, q = '', fraudOnly = false } = {}) {
  const res = await client.get('/api/transactions', {
    params: { skip, limit, q: q || undefined, fraud_only: fraudOnly },
  })
  return res.data
}
// idempotencyKey: one per submission, so a retried or double-clicked submit records it once
export async function createTransaction(data, idempotencyKey) {
  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}
  return (await client.post('/api/transactions', data, { headers })).data
}
export async function deleteTransaction(uid) {
  return (await client.delete(`/api/transactions/${uid}`)).data
}
export async function uploadTransactionsCSV(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post('/api/transactions/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
