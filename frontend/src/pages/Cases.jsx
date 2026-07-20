import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert as MuiAlert,
  Table, TableHead, TableBody, TableRow, TableCell, TablePagination, TextField,
  MenuItem, Select, InputAdornment, LinearProgress, Snackbar, Dialog, DialogTitle,
  DialogContent, DialogActions, IconButton, Divider,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import VisibilityIcon from '@mui/icons-material/Visibility'
import RiskChip from '../components/RiskChip'
import ConfirmDialog from '../components/ConfirmDialog'
import { getCasesSummary, listCases, getCase, createCase, updateCase, deleteCase } from '../api/cases'

const STATUSES = ['Open', 'Under Investigation', 'Confirmed Fraud', 'False Positive', 'Closed']
const STATUS_COLOR = {
  'Open': 'info', 'Under Investigation': 'warning',
  'Confirmed Fraud': 'error', 'False Positive': 'default', 'Closed': 'success',
}
const EMPTY = { account_uid: '', alert_uid: '', assigned_to: '', notes: '' }

export default function Cases() {
  const [summary, setSummary] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [detail, setDetail] = useState(null)       // full case with joined info
  const [editForm, setEditForm] = useState(null)   // {assigned_to, notes, status, final_decision}
  const [deleteUid, setDeleteUid] = useState(null)

  const loadSummary = useCallback(() => getCasesSummary().then(setSummary).catch(() => {}), [])
  const loadRows = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listCases({ skip: page * rowsPerPage, limit: rowsPerPage, status: statusFilter, q })
      setRows(data.items); setTotal(data.total)
    } finally { setLoading(false) }
  }, [page, rowsPerPage, statusFilter, q])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { loadRows() }, [loadRows])
  useEffect(() => {
    const t = setTimeout(() => { setPage(0); setQ(search) }, 400)
    return () => clearTimeout(t)
  }, [search])

  async function handleCreate() {
    setError('')
    try {
      const body = { ...form, alert_uid: form.alert_uid || null }
      const c = await createCase(body)
      setToast(`${c.case_uid} created`)
      setCreateOpen(false); setForm(EMPTY)
      loadSummary(); loadRows()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not create the case.')
    }
  }

  async function openDetail(uid) {
    const c = await getCase(uid)
    setDetail(c)
    setEditForm({
      assigned_to: c.assigned_to, notes: c.notes,
      status: c.status, final_decision: c.final_decision,
    })
  }

  async function handleSave() {
    try {
      await updateCase(detail.case_uid, editForm)
      setToast(`${detail.case_uid} updated`)
      setDetail(null)
      loadSummary(); loadRows()
    } catch (err) {
      setError(err?.response?.data?.detail || 'Update failed.')
    }
  }

  async function handleDelete() {
    await deleteCase(deleteUid)
    setToast(`${deleteUid} deleted`)
    setDeleteUid(null)
    loadSummary(); loadRows()
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Investigations</Typography>
          <Typography variant="body2" color="text.secondary">
            Fraud investigation case management (workflow Step 13)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setForm(EMPTY); setCreateOpen(true) }}>
          New case
        </Button>
      </Stack>

      {error && <MuiAlert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</MuiAlert>}

      {summary && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} sm={2}>
            <Paper sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="h5">{summary.total.toLocaleString('en-IN')}</Typography>
              <Typography variant="caption" color="text.secondary">Total cases</Typography>
            </Paper>
          </Grid>
          {STATUSES.map((s) => (
            <Grid item xs={6} sm={2} key={s}>
              <Paper
                sx={{ p: 2, textAlign: 'center', cursor: 'pointer',
                      outline: statusFilter === s ? '2px solid' : 'none', outlineColor: 'primary.main' }}
                onClick={() => { setPage(0); setStatusFilter(statusFilter === s ? '' : s) }}>
                <Typography variant="h5">{summary.by_status[s]?.toLocaleString('en-IN') ?? 0}</Typography>
                <Typography variant="caption" color="text.secondary">{s}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      <Paper sx={{ p: 2 }}>
        <TextField
          size="small" placeholder="Search case, account, alert or officer…" value={search}
          onChange={(e) => setSearch(e.target.value)} sx={{ width: 340, mb: 2 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
        />
        {loading && <LinearProgress sx={{ mb: 1 }} />}
        <Table size="small" sx={{ opacity: loading ? 0.6 : 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>Case</TableCell>
              <TableCell>Account</TableCell>
              <TableCell>Alert</TableCell>
              <TableCell>Assigned to</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Final decision</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.case_uid} hover>
                <TableCell sx={{ fontFamily: 'monospace' }}>{r.case_uid}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{r.account_uid}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{r.alert_uid || '—'}</TableCell>
                <TableCell>{r.assigned_to || '—'}</TableCell>
                <TableCell><Chip size="small" label={r.status} color={STATUS_COLOR[r.status]} /></TableCell>
                <TableCell sx={{ maxWidth: 220 }}>
                  <Typography variant="body2" noWrap title={r.final_decision}>{r.final_decision || '—'}</Typography>
                </TableCell>
                <TableCell>{r.created_at ? new Date(r.created_at).toLocaleDateString('en-IN') : '—'}</TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => openDetail(r.case_uid)}><VisibilityIcon fontSize="small" /></IconButton>
                  <IconButton size="small" color="error" onClick={() => setDeleteUid(r.case_uid)}><DeleteIcon fontSize="small" /></IconButton>
                </TableCell>
              </TableRow>
            ))}
            {!loading && rows.length === 0 && (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                No cases yet — create one here, or from any alert on the Fraud Alerts page.
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
        <TablePagination
          component="div" count={total} page={page} onPageChange={(e, p) => setPage(p)}
          rowsPerPage={rowsPerPage} rowsPerPageOptions={[10, 25, 50]}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0) }}
        />
      </Paper>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New investigation case</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Account UID *" value={form.account_uid} size="small"
              onChange={(e) => setForm({ ...form, account_uid: e.target.value.trim() })}
              placeholder="e.g. ACC01234" />
            <TextField label="Alert UID (optional)" value={form.alert_uid} size="small"
              onChange={(e) => setForm({ ...form, alert_uid: e.target.value.trim() })}
              placeholder="e.g. ALT000123 — links the case to an alert" />
            <TextField label="Assigned to" value={form.assigned_to} size="small"
              onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
              placeholder="Investigator name" />
            <TextField label="Notes" value={form.notes} multiline minRows={3}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Initial observations…" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!form.account_uid} onClick={handleCreate}>Create case</Button>
        </DialogActions>
      </Dialog>

      {/* Detail / edit dialog */}
      <Dialog open={!!detail} onClose={() => setDetail(null)} maxWidth="md" fullWidth>
        {detail && editForm && (
          <>
            <DialogTitle>
              {detail.case_uid}
              <Typography variant="body2" color="text.secondary">
                Account {detail.account_uid}{detail.account ? ` — ${detail.account.customer_name}` : ''}
                {detail.account && <> · <RiskChip level={detail.account.risk_level} /> · score {(detail.account.fraud_score * 100).toFixed(0)}%</>}
              </Typography>
            </DialogTitle>
            <DialogContent dividers>
              {detail.alert && (
                <Paper variant="outlined" sx={{ p: 1.5, mb: 2, bgcolor: '#f8fafc' }}>
                  <Typography variant="caption" color="text.secondary">Linked alert {detail.alert_uid}</Typography>
                  <Typography variant="body2">{detail.alert.reason}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {detail.alert.transaction_uid ? `Transaction ${detail.alert.transaction_uid} · ` : ''}
                    Alert status: {detail.alert.status}
                  </Typography>
                </Paper>
              )}
              <Stack spacing={2}>
                <Stack direction="row" spacing={2}>
                  <TextField label="Assigned to" size="small" fullWidth value={editForm.assigned_to}
                    onChange={(e) => setEditForm({ ...editForm, assigned_to: e.target.value })} />
                  <TextField select label="Status" size="small" sx={{ minWidth: 220 }} value={editForm.status}
                    onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                    {STATUSES.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                  </TextField>
                </Stack>
                <TextField label="Investigation notes" multiline minRows={4} value={editForm.notes}
                  onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} />
                <TextField label="Final decision" value={editForm.final_decision}
                  placeholder="e.g. Mule account confirmed; recommend freeze and SAR filing."
                  onChange={(e) => setEditForm({ ...editForm, final_decision: e.target.value })} />
                {(editForm.status === 'Confirmed Fraud' || editForm.status === 'False Positive') && detail.alert_uid && (
                  <MuiAlert severity="info">
                    Saving with this status will also mark the linked alert as "{editForm.status}".
                  </MuiAlert>
                )}
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDetail(null)}>Cancel</Button>
              <Button variant="contained" startIcon={<EditIcon />} onClick={handleSave}>Save</Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      <ConfirmDialog
        open={!!deleteUid}
        title="Delete case?"
        message={`This will permanently delete ${deleteUid}.`}
        onCancel={() => setDeleteUid(null)}
        onConfirm={handleDelete}
      />
      <Snackbar open={!!toast} autoHideDuration={2500} onClose={() => setToast('')} message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  )
}
