import client, { API_URL } from './client'

export async function listNotifications({ skip = 0, limit = 25, unreadOnly = false } = {}) {
  return (await client.get('/api/notifications', {
    params: { skip, limit, unread_only: unreadOnly || undefined },
  })).data
}
export async function markNotificationRead(id) {
  return (await client.post(`/api/notifications/${id}/read`)).data
}
export async function markNotificationUnread(id) {
  return (await client.post(`/api/notifications/${id}/unread`)).data
}
export async function markAllNotificationsRead() {
  return (await client.post('/api/notifications/read-all')).data
}

// The live stream: ws(s)://<backend>/api/notifications/ws
export const NOTIFICATIONS_WS_URL = API_URL.replace(/^http/, 'ws') + '/api/notifications/ws'
