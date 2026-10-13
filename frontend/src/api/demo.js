import client from './client'

// The demo scenario's stages, rule hits, accounts, rings and network, as detection recorded them
export async function getDemoScenario() {
  return (await client.get('/api/demo/scenario')).data
}
