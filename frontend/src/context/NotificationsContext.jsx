import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Snackbar } from '@mui/material'
import { useAuth } from './AuthContext'
import {
  listNotifications, markAllNotificationsRead, markNotificationRead, markNotificationUnread,
  NOTIFICATIONS_WS_URL,
} from '../api/notifications'

const NotificationsContext = createContext(null)
const RECENT = 10
const ANALYST_ROLES = ['admin', 'analyst']

export const isFraudAnalyst = (user) => ANALYST_ROLES.includes((user?.role || '').toLowerCase())
export const notificationLink = (n) =>
  `/accounts/${encodeURIComponent(n.account_uid)}${n.transaction_uid ? `?txn=${encodeURIComponent(n.transaction_uid)}` : ''}`

// Keeps a live WebSocket to the backend for fraud analysts: new notifications
// arrive without a refresh, and a dropped connection reconnects (with backoff)
// and catches up on whatever it missed. The list itself is stored server-side.
export function NotificationsProvider({ children }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const enabled = isFraudAnalyst(user)
  const [recent, setRecent] = useState([])
  const [unread, setUnread] = useState(0)
  const [connection, setConnection] = useState('offline')   // connecting | live | offline
  const [version, setVersion] = useState(0)                 // bumps on every change, for pages to refetch
  const [toast, setToast] = useState(null)
  const lastId = useRef(null)

  const refresh = useCallback(async () => {
    const data = await listNotifications({ limit: RECENT })
    setRecent(data.items)
    setUnread(data.unread)
    const newest = data.items[0]?.id ?? 0
    lastId.current = Math.max(lastId.current ?? 0, newest)
  }, [])

  useEffect(() => {
    if (!enabled) return undefined
    let ws = null
    let stopped = false
    let attempt = 0
    let timer = null

    async function connect() {
      if (lastId.current === null) {
        try { await refresh() } catch { /* the stream still works; it starts from now */ }
      }
      const token = localStorage.getItem('token')
      if (stopped || !token) return
      setConnection('connecting')
      ws = new WebSocket(NOTIFICATIONS_WS_URL)
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token, after_id: lastId.current }))
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'ready') {
          attempt = 0
          setConnection('live')
          setUnread(msg.unread)
        } else if (msg.type === 'notification') {
          const n = msg.notification
          lastId.current = Math.max(lastId.current ?? 0, n.id)
          setRecent((prev) => [n, ...prev.filter((p) => p.id !== n.id)].slice(0, RECENT))
          setUnread(msg.unread)
          setVersion((v) => v + 1)
          setToast(n)
        } else if (msg.type === 'unread') {
          setUnread(msg.unread)
          setVersion((v) => v + 1)
        }
      }
      ws.onclose = (event) => {
        setConnection('offline')
        if (stopped || event.code === 4401 || event.code === 4403) return   // log in again / not allowed
        const delay = Math.min(30000, 1000 * 2 ** attempt)
        attempt += 1
        timer = setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      if (ws) ws.close()
    }
  }, [enabled, refresh])

  const applyRead = useCallback((id, read, count) => {
    setRecent((prev) => prev.map((n) => (n.id === id ? { ...n, read } : n)))
    setUnread(count)
    setVersion((v) => v + 1)
  }, [])

  const markRead = useCallback(async (id) => {
    const res = await markNotificationRead(id)
    applyRead(id, true, res.unread)
  }, [applyRead])

  const markUnread = useCallback(async (id) => {
    const res = await markNotificationUnread(id)
    applyRead(id, false, res.unread)
  }, [applyRead])

  const markAllRead = useCallback(async () => {
    const res = await markAllNotificationsRead()
    setRecent((prev) => prev.map((n) => ({ ...n, read: true })))
    setUnread(res.unread)
    setVersion((v) => v + 1)
  }, [])

  async function openToast() {
    const n = toast
    setToast(null)
    if (!n) return
    try { await markRead(n.id) } catch { /* still open it */ }
    navigate(notificationLink(n))
  }

  const dismissToast = useCallback(() => setToast(null), [])
  const value = { enabled, recent, unread, connection, version, refresh, markRead, markUnread, markAllRead, dismissToast }
  return (
    <NotificationsContext.Provider value={value}>
      {children}
      <Snackbar open={!!toast} onClose={(e, reason) => reason !== 'clickaway' && setToast(null)}
        autoHideDuration={12000} anchorOrigin={{ vertical: 'top', horizontal: 'right' }} sx={{ mt: 7 }}>
        <Alert severity="error" variant="filled" onClose={() => setToast(null)} sx={{ maxWidth: 440 }}
          action={<Button color="inherit" size="small" onClick={openToast}>Investigate</Button>}>
          {toast?.message}
        </Alert>
      </Snackbar>
    </NotificationsContext.Provider>
  )
}

export function useNotifications() {
  return useContext(NotificationsContext)
}
