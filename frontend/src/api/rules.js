import client from './client'

export async function getRulesStatus() {
  return (await client.get('/api/rules/status')).data
}
export async function runRules() {
  // rule engine scans 80k txns; allow a few minutes
  return (await client.post('/api/rules/run', null, { timeout: 600000 })).data
}
