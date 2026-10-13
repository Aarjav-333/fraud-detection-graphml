import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Badge, Box, Button, Chip, Divider, IconButton, List, ListItemButton, Popover, Stack, Tooltip, Typography,
} from '@mui/material'
import NotificationsIcon from '@mui/icons-material/Notifications'
import NotificationsNoneIcon from '@mui/icons-material/NotificationsNone'
import { notificationLink, useNotifications } from '../context/NotificationsContext'

const CONNECTION = {
  live: { label: 'Live', color: 'success.main' },
  connecting: { label: 'Connecting…', color: 'text.disabled' },
  offline: { label: 'Reconnecting…', color: 'text.disabled' },
}

export function timeAgo(iso) {
  if (!iso) return ''
  const seconds = Math.max(0, (Date.now() - new Date(iso.endsWith('Z') ? iso : iso + 'Z')) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return `${Math.floor(seconds / 86400)} d ago`
}

export default function NotificationBell() {
  const notifications = useNotifications()
  const navigate = useNavigate()
  const [anchor, setAnchor] = useState(null)
  if (!notifications?.enabled) return null
  const { recent, unread, connection, markRead, markAllRead, dismissToast } = notifications
  const conn = CONNECTION[connection] || CONNECTION.offline

  async function open(n) {
    setAnchor(null)
    if (!n.read) {
      try { await markRead(n.id) } catch { /* still open it */ }
    }
    navigate(notificationLink(n))
  }

  return (
    <>
      <Tooltip title={unread ? `${unread} unread fraud alert${unread === 1 ? '' : 's'}` : 'Fraud alerts'}>
        <IconButton onClick={(e) => { dismissToast(); setAnchor(e.currentTarget) }} aria-label="Fraud alert notifications">
          <Badge badgeContent={unread} color="error" max={99}>
            {unread ? <NotificationsIcon /> : <NotificationsNoneIcon />}
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 400, maxWidth: 'calc(100vw - 32px)' } } }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1.5 }}>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Fraud alerts</Typography>
            <Stack direction="row" spacing={0.75} alignItems="center">
              <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: conn.color }} />
              <Typography variant="caption" color="text.secondary">{conn.label}</Typography>
            </Stack>
          </Box>
          <Button size="small" disabled={!unread} onClick={markAllRead}>Mark all read</Button>
        </Stack>
        <Divider />
        {recent.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ p: 3, textAlign: 'center' }}>
            No fraud alerts yet. You'll be notified here the moment an account confirmed as fraud makes a transaction.
          </Typography>
        ) : (
          <List dense disablePadding sx={{ maxHeight: 420, overflowY: 'auto' }}>
            {recent.map((n) => (
              <ListItemButton key={n.id} onClick={() => open(n)} divider
                sx={{ alignItems: 'flex-start', gap: 1.25, py: 1.25, bgcolor: n.read ? 'transparent' : 'rgba(220,38,38,0.05)' }}>
                <Box sx={{ width: 8, height: 8, mt: 0.9, borderRadius: '50%', flexShrink: 0,
                           bgcolor: n.read ? 'transparent' : 'error.main' }} aria-label={n.read ? 'read' : 'unread'} />
                <Box sx={{ minWidth: 0 }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                    <Chip size="small" color="error" label={`${n.priority} priority`} sx={{ height: 20, fontSize: 11 }} />
                    <Typography variant="caption" color="text.secondary">{timeAgo(n.created_at)}</Typography>
                  </Stack>
                  <Typography variant="body2" sx={{ fontWeight: n.read ? 400 : 600 }}>{n.message}</Typography>
                </Box>
              </ListItemButton>
            ))}
          </List>
        )}
        <Divider />
        <Box sx={{ p: 1, textAlign: 'center' }}>
          <Button size="small" onClick={() => { setAnchor(null); navigate('/notifications') }}>
            View notification history
          </Button>
        </Box>
      </Popover>
    </>
  )
}
