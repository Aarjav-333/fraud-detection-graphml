import client from './client'

export async function listTransactions({ skip = 0, limit = 25, q = '', fraudOnly = false } = {}) {
  const res = await client.get('/api/transactions', {
    params: { skip, limit, q: q || undefined, fraud_only: fraudOnly },
  })
  return res.data
}
export async function createTransaction(data) {
  return (await client.post('/api/transactions', data)).data
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
