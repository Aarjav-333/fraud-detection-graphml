import client from './client'

export async function getInvestigation(uid) {
  return (await client.get(`/api/accounts/${uid}/investigation`)).data
}

// action: 'under_review' | 'confirm_fraud' | 'clear'
export async function reviewAccount(uid, { action, note = '', transactionUid = null }) {
  return (await client.post(`/api/accounts/${uid}/review`, {
    action, note, transaction_uid: transactionUid || null,
  })).data
}

export async function retryEmail(uid, deliveryId) {
  return (await client.post(`/api/accounts/${uid}/emails/${deliveryId}/retry`)).data
}
