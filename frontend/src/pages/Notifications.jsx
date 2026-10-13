import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import {
  Alert, Box, Button, Chip, IconButton, LinearProgress, Link, Paper, Stack, Table, TableBody, TableCell,
  TableHead, TablePagination, TableRow, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material'
import MarkEmailReadOutlinedIcon from '@mui/icons-material/MarkEmailReadOutlined'
import MarkEmailUnreadOutlinedIcon from '@mui/icons-material/MarkEmailUnreadOutlined'
import { listNotifications } from '../api/notifications'
import { notificationLink, useNotifications } from '../context/NotificationsContext'
import FraudStatusChip from '../components/FraudStatusChip'
import { eventTime, money, pct, txnTime } from '../utils/format'

export default function Notifications() {
  const live = useNotifications()
  const navigate = useNavigate()
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await listNotifications({ skip: page * rowsPerPage, limit: rowsPerPage, unreadOnly: filter === 'unread' }))
      setError('')
    } catch (err) {
      setError(err?.response?.status === 403
        ? 'Fraud notifications are for fraud analyst accounts.'
        : 'Could not load notifications. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, filter])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (live?.version) load() }, [live?.version, load])   // new or read elsewhere

  async function toggleRead(n) {
    if (n.read) await live.markUnread(n.id)
    else await live.markRead(n.id)
  }

  async function open(n) {
    if (!n.read) {
      try { await live.markRead(n.id) } catch { /* still open it */ }
    }
    navigate(notificationLink(n))
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Notifications</Typography>
          <Typography variant="body2" color="text.secondary">
            Every alert about activity by accounts confirmed as fraud — kept after refreshes and logins
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Chip size="small" variant="outlined" label={live?.connection === 'live' ? 'Live updates on' : 'Reconnecting…'}
            color={live?.connection === 'live' ? 'success' : 'default'} />
          <Button variant="outlined" disabled={!live?.unread} onClick={() => live.markAllRead()}>Mark all read</Button>
        </Stack>
      </Stack>

      {error && <Alert severity={error.includes('analyst') ? 'warning' : 'error'} sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ p: 2 }}>
        <ToggleButtonGroup exclusive size="small" value={filter} sx={{ mb: 2 }}
          onChange={(e, v) => { if (v) { setFilter(v); setPage(0) } }}>
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="unread">Unread ({live?.unread ?? 0})</ToggleButton>
        </ToggleButtonGroup>
        {loading && <LinearProgress sx={{ mb: 1 }} />}
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ opacity: loading ? 0.6 : 1 }}>
            <TableHead>
              <TableRow>
                <TableCell>Priority</TableCell>
                <TableCell>Alert</TableCell>
                <TableCell>Account</TableCell>
                <TableCell>Transaction</TableCell>
                <TableCell align="right">Amount</TableCell>
                <TableCell>Transaction time</TableCell>
                <TableCell>Account status</TableCell>
                <TableCell align="right">Risk score</TableCell>
                <TableCell>Notified</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(data?.items || []).map((n) => (
                <TableRow key={n.id} hover sx={{ cursor: 'pointer', bgcolor: n.read ? undefined : 'rgba(220,38,38,0.04)' }}
                  onClick={() => open(n)}>
                  <TableCell onClick={(e) => e.stopPropagation()} sx={{ whiteSpace: 'nowrap' }}>
                    <Tooltip title={n.read ? 'Mark as unread' : 'Mark as read'}>
                      <IconButton size="small" onClick={() => toggleRead(n)} aria-label={n.read ? 'Mark as unread' : 'Mark as read'}>
                        {n.read ? <MarkEmailUnreadOutlinedIcon fontSize="small" /> : <MarkEmailReadOutlinedIcon fontSize="small" color="error" />}
                      </IconButton>
                    </Tooltip>
                    <Chip size="small" color="error" label={n.priority} variant={n.read ? 'outlined' : 'filled'} sx={{ ml: 0.5 }} />
                  </TableCell>
                  <TableCell sx={{ minWidth: 260, maxWidth: 380 }}>
                    <Typography variant="body2" sx={{ fontWeight: n.read ? 400 : 600 }}>{n.message}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{n.alert_uid}</Typography>
                  </TableCell>
                  <TableCell>
                    <Link component={RouterLink} to={notificationLink(n)} onClick={(e) => e.stopPropagation()}
                      sx={{ fontFamily: 'monospace', fontWeight: n.read ? 400 : 700 }}>{n.account_uid}</Link>
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{n.transaction_uid}</TableCell>
                  <TableCell align="right">{money(n.amount)}</TableCell>
                  <TableCell>{txnTime(n.transaction_time)}</TableCell>
                  <TableCell><FraudStatusChip status={n.account_status} /></TableCell>
                  <TableCell align="right">{pct(n.risk_score)}</TableCell>
                  <TableCell>{eventTime(n.created_at)}</TableCell>
                </TableRow>
              ))}
              {data && data.items.length === 0 && (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  {filter === 'unread' ? 'No unread notifications.'
                    : 'No notifications yet. They appear here when an account an analyst confirmed as fraud makes a new transaction.'}
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Box>
        <TablePagination
          component="div" count={data?.total || 0} page={page} onPageChange={(e, p) => setPage(p)}
          rowsPerPage={rowsPerPage} rowsPerPageOptions={[10, 25, 50, 100]}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0) }}
        />
      </Paper>
    </Box>
  )
}
