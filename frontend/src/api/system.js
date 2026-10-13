import client from './client'

// Which backend this is: the normal app, or the standalone demo ({ demo_mode: 'standalone' })
export async function getSystemInfo() {
  return (await client.get('/api/system/info')).data
}
