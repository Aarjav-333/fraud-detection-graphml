import client from './client'

export async function getDashboardStats() {
  return (await client.get('/api/dashboard/stats')).data
}
