import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert as MuiAlert,
  Table, TableHead, TableBody, TableRow, TableCell, TablePagination, TextField,
  MenuItem, Select, InputAdornment, LinearProgress, Snackbar, Slider,
} from '@mui/material'
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive'
import FolderSharedIcon from '@mui/icons-material/FolderShared'
import SearchIcon from '@mui/icons-material/Search'
import RiskChip from '../components/RiskChip'
import { generateAlerts, getAlertsSummary, listAlerts, updateAlertStatus } from '../api/alerts'
import { createCase } from '../api/cases'

const STATUSES = ['Pending', 'Under Review', 'Confirmed Fraud', 'False Positive', 'Resolved']
const STATUS_COLOR = {
  'Pending': 'default', 'Under Review': 'info',
  'Confirmed Fraud': 'error', 'False Positive': 'warning', 'Resolved': 'success',
}

export default function Alerts() {
  const [summary, setSummary] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [statusFilter, setStatusFilter] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [threshold, setThreshold] = useState(0.8)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')

  const loadSummary = useCallback(() => getAlertsSummary().then(setSummary).catch(() => {}), [])

  const loadRows = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listAlerts({
        skip: page * rowsPerPage, limit: rowsPerPage,
        status: statusFilter, risk: riskFilter, q,
      })
      setRows(data.items)
      setTotal(data.total)
    } finally { setLoading(false) }
  }, [page, rowsPerPage, statusFilter, riskFilter, q])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { loadRows() }, [loadRows])
  useEffect(() => {
    const t = setTimeout(() => { setPage(0); setQ(search) }, 400)
    return () => clearTimeout(t)
  }, [search])

  async function handleGenerate() {
    setGenerating(true); setError('')
    try {
      const res = await generateAlerts(threshold)
      setToast(`Created ${res.created_rule_alerts} rule alert(s) + ${res.created_ml_alerts} ML alert(s).`)
      await Promise.all([loadSummary(), loadRows()])
    } catch (err) {
      setError(err?.response?.data?.detail || 'Generation failed — run Rule Detection and ML Scoring first.')
    } finally { setGenerating(false) }
  }

  async function handleStatusChange(uid, status) {
    await updateAlertStatus(uid, status)
    setToast(`${uid} → ${status}`)
    loadSummary()
    setRows((prev) => prev.map((r) => (r.alert_uid === uid ? { ...r, status } : r)))
  }

  async function handleCreateCase(alert) {
    try {
      const c = await createCase({ account_uid: alert.account_uid, alert_uid: alert.alert_uid })
      setToast(`${c.case_uid} opened for ${alert.alert_uid}`)
      loadSummary(); loadRows()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not create case.')
    }
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Fraud Alerts</Typography>
          <Typography variant="body2" color="text.secondary">
            Alerts raised by the rule engine and ML scoring (workflow Step 11)
          </Typography>
        </Box>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box sx={{ width: 180 }}>
            <Typography variant="caption" color="text.secondary">
              ML threshold: {(threshold * 100).toFixed(0)}%
            </Typography>
            <Slider size="small" min={0.5} max={0.95} step={0.05} value={threshold}
              onChange={(e, v) => setThreshold(v)} />
          </Box>
          <Button variant="contained" startIcon={<NotificationsActiveIcon />}
            onClick={handleGenerate} disabled={generating}>
            {generating ? 'Generating…' : 'Generate alerts'}
          </Button>
        </Stack>
      </Stack>

      {error && <MuiAlert severity="error" sx={{ mb: 2 }}>{error}</MuiAlert>}

      {summary && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} sm={2}>
            <Paper sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h5">{summary.total.toLocaleString('en-IN')}</Typography>
              <Typography variant="caption" color="text.secondary">Total alerts</Typography>
            </Paper>
          </Grid>
          {STATUSES.map((s) => (
            <Grid item xs={6} sm={2} key={s}>
              <Paper
                sx={{ p: 2, textAlign: 'center', cursor: 'pointer',
                      outline: statusFilter === s ? '2px solid' : 'none', outlineColor: 'primary.main' }}
                onClick={() => { setPage(0); setStatusFilter(statusFilter === s ? '' : s) }}
              >
                <Typography variant="h5">{summary.by_status[s]?.toLocaleString('en-IN') ?? 0}</Typography>
                <Typography variant="caption" color="text.secondary">{s}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <TextField
            size="small" placeholder="Search alert, account or txn UID…" value={search}
            onChange={(e) => setSearch(e.target.value)} sx={{ width: 320 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          />
          <TextField select size="small" label="Risk" value={riskFilter} sx={{ width: 140 }}
            onChange={(e) => { setPage(0); setRiskFilter(e.target.value) }}>
            <MenuItem value="">All</MenuItem>
            <MenuItem value="High">High</MenuItem>
            <MenuItem value="Medium">Medium</MenuItem>
            <MenuItem value="Low">Low</MenuItem>
          </TextField>
        </Stack>

        {loading && <LinearProgress sx={{ mb: 1 }} />}
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ opacity: loading ? 0.6 : 1 }}>
            <TableHead>
              <TableRow>
                <TableCell>Alert</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Target</TableCell>
                <TableCell>Reason</TableCell>
                <TableCell align="right">Score</TableCell>
                <TableCell>Risk</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Case</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.alert_uid} hover>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{r.alert_uid}</TableCell>
                  <TableCell>
                    <Chip size="small" label={r.type} variant="outlined"
                      color={r.type === 'Account' ? 'secondary' : 'default'} />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {r.transaction_uid || r.account_uid}
                  </TableCell>
                  <TableCell sx={{ maxWidth: 320 }}>
                    <Typography variant="body2" noWrap title={r.reason}>{r.reason}</Typography>
                  </TableCell>
                  <TableCell align="right">{(r.fraud_score * 100).toFixed(1)}%</TableCell>
                  <TableCell><RiskChip level={r.risk_level} /></TableCell>
                  <TableCell>
                    <Select size="small" value={r.status} sx={{ minWidth: 150, fontSize: 13 }}
                      onChange={(e) => handleStatusChange(r.alert_uid, e.target.value)}>
                      {STATUSES.map((s) => (
                        <MenuItem key={s} value={s}>
                          <Chip size="small" label={s} color={STATUS_COLOR[s]}
                            variant={s === 'Pending' ? 'outlined' : 'filled'} />
                        </MenuItem>
                      ))}
                    </Select>
                  </TableCell>
                  <TableCell>{r.created_at ? new Date(r.created_at).toLocaleDateString('en-IN') : '—'}</TableCell>
                  <TableCell align="right">
                    <Button size="small" startIcon={<FolderSharedIcon />} onClick={() => handleCreateCase(r)}>
                      Open case
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  No alerts yet — run Rule Detection and ML Scoring, then click "Generate alerts".
                </TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </Box>
        <TablePagination
          component="div" count={total} page={page} onPageChange={(e, p) => setPage(p)}
          rowsPerPage={rowsPerPage} rowsPerPageOptions={[10, 25, 50, 100]}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0) }}
        />
      </Paper>

      <Snackbar open={!!toast} autoHideDuration={2500} onClose={() => setToast('')} message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  )
}
