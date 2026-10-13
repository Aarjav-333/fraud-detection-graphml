import { useEffect, useState, useCallback } from 'react'
import { Link as RouterLink, useSearchParams } from 'react-router-dom'
import {
  Box, Typography, Paper, Table, TableHead, TableBody, TableRow, TableCell,
  TablePagination, TextField, Button, IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, Stack, MenuItem, Chip, InputAdornment, Tooltip, CircularProgress, Alert, Link,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import EditIcon from '@mui/icons-material/Edit'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RiskChip, { RISK_LEVELS } from '../components/RiskChip'
import FraudStatusChip, { FRAUD_STATUSES } from '../components/FraudStatusChip'
import ConfirmDialog from '../components/ConfirmDialog'
import {
  listAccounts, createAccount, updateAccount, deactivateAccount, activateAccount,
} from '../api/accounts'

const ACCOUNT_TYPES = ['Savings', 'Current', 'Wallet', 'Business']
// onboarding_risk_category is a manual KYC assessment; the risk level itself is computed by the rule engine
const EMPTY = { customer_name: '', email: '', phone: '', account_type: 'Savings', onboarding_risk_category: '' }

// The API's error as text: a message string, or FastAPI's list of validation errors.
// Anything else falls back to a generic message rather than being rendered as-is.
function errorText(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.filter((d) => typeof d?.msg === 'string').map((d) => {
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null
      const msg = d.msg.replace(/^Value error, /, '')
      return d.type === 'extra_forbidden' && typeof field === 'string' ? `${field}: ${msg}` : msg
    })
    if (parts.length) return parts.join(' ')
  }
  return fallback
}

export default function Accounts() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [params, setParams] = useSearchParams()
  const fraudStatus = FRAUD_STATUSES.includes(params.get('status')) ? params.get('status') : ''

  const [dialog, setDialog] = useState({ open: false, mode: 'add', uid: null })
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [confirm, setConfirm] = useState({ open: false, uid: null })

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listAccounts({ skip: page * rowsPerPage, limit: rowsPerPage, q, fraudStatus })
      setRows(data.items)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, q, fraudStatus])

  useEffect(() => { fetchData() }, [fetchData])

  // debounce the search box
  useEffect(() => {
    const t = setTimeout(() => { setPage(0); setQ(search) }, 400)
    return () => clearTimeout(t)
  }, [search])

  function openAdd() {
    setForm(EMPTY); setFormError(''); setDialog({ open: true, mode: 'add', uid: null })
  }
  function openEdit(row) {
    setForm({
      customer_name: row.customer_name || '', email: row.email || '', phone: row.phone || '',
      account_type: row.account_type || 'Savings', onboarding_risk_category: row.onboarding_risk_category || '',
    })
    setFormError('')
    setDialog({ open: true, mode: 'edit', uid: row.account_uid, riskLevel: row.risk_level || 'Low' })
  }

  async function handleSave() {
    setFormError('')
    if (!form.customer_name.trim()) { setFormError('Customer name is required'); return }
    const body = { ...form, onboarding_risk_category: form.onboarding_risk_category || null }
    try {
      if (dialog.mode === 'add') await createAccount(body)
      else await updateAccount(dialog.uid, body)
      setDialog((d) => ({ ...d, open: false }))   // keep its content while it fades out
      fetchData()
    } catch (err) {
      setFormError(errorText(err, 'Could not save account'))
    }
  }

  async function toggleActive(row) {
    if (row.is_active) setConfirm({ open: true, uid: row.account_uid })
    else { await activateAccount(row.account_uid); fetchData() }
  }
  async function doDeactivate() {
    await deactivateAccount(confirm.uid)
    setConfirm({ open: false, uid: null })
    fetchData()
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Accounts</Typography>
          <Typography variant="body2" color="text.secondary">
            {total.toLocaleString('en-IN')} customer accounts
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openAdd}>Add account</Button>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <TextField
            size="small" placeholder="Search by name, UID or email…" value={search}
            onChange={(e) => setSearch(e.target.value)} sx={{ width: 340 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          />
          <TextField select size="small" label="Fraud status" value={fraudStatus} sx={{ width: 190 }}
            onChange={(e) => { setPage(0); setParams(e.target.value ? { status: e.target.value } : {}) }}>
            <MenuItem value="">All</MenuItem>
            {FRAUD_STATUSES.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </TextField>
        </Stack>
        <Box sx={{ overflowX: 'auto', position: 'relative' }}>
          {loading && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', justifyContent: 'center', pt: 4, zIndex: 1 }}>
              <CircularProgress size={26} />
            </Box>
          )}
          <Table size="small" sx={{ opacity: loading ? 0.5 : 1 }}>
            <TableHead>
              <TableRow>
                <TableCell>Account UID</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Email</TableCell>
                <TableCell>Phone</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>
                  <Tooltip title="Computed by the rule engine each time Rule Detection runs">
                    <span>Risk (rules)</span>
                  </Tooltip>
                </TableCell>
                <TableCell>Fraud status</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.account_uid} hover>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    <Link component={RouterLink} to={`/accounts/${encodeURIComponent(r.account_uid)}`} underline="hover">
                      {r.account_uid}
                    </Link>
                  </TableCell>
                  <TableCell>{r.customer_name}</TableCell>
                  <TableCell>{r.email}</TableCell>
                  <TableCell>{r.phone}</TableCell>
                  <TableCell>{r.account_type}</TableCell>
                  <TableCell><RiskChip level={r.risk_level} /></TableCell>
                  <TableCell><FraudStatusChip status={r.fraud_status} /></TableCell>
                  <TableCell>
                    <Chip size="small" label={r.is_active ? 'Active' : 'Inactive'}
                      color={r.is_active ? 'default' : 'error'} variant={r.is_active ? 'outlined' : 'filled'} />
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Edit"><IconButton size="small" onClick={() => openEdit(r)}><EditIcon fontSize="small" /></IconButton></Tooltip>
                    <Tooltip title={r.is_active ? 'Deactivate' : 'Activate'}>
                      <IconButton size="small" onClick={() => toggleActive(r)}>
                        {r.is_active ? <BlockIcon fontSize="small" color="error" /> : <CheckCircleIcon fontSize="small" color="success" />}
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>No accounts found</TableCell></TableRow>
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

      {/* Add / Edit dialog */}
      <Dialog open={dialog.open} onClose={() => setDialog({ ...dialog, open: false })} fullWidth maxWidth="sm">
        <DialogTitle>{dialog.mode === 'add' ? 'Add account' : `Edit ${dialog.uid}`}</DialogTitle>
        <DialogContent>
          {formError && <Alert severity="error" sx={{ mb: 2 }}>{formError}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Customer name" value={form.customer_name} required
              onChange={(e) => setForm({ ...form, customer_name: e.target.value })} />
            <TextField label="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <TextField label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <TextField select label="Account type" value={form.account_type}
              onChange={(e) => setForm({ ...form, account_type: e.target.value })}>
              {ACCOUNT_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </TextField>
            <TextField select label="Onboarding risk category (KYC)" value={form.onboarding_risk_category}
              SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
              onChange={(e) => setForm({ ...form, onboarding_risk_category: e.target.value })}
              helperText="Your assessment when the customer was onboarded. Kept separate from the computed risk level below.">
              <MenuItem value=""><em>Not assessed</em></MenuItem>
              {RISK_LEVELS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </TextField>
            <Box sx={{ p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                Risk level — computed by the rule engine (read-only)
              </Typography>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <RiskChip level={dialog.mode === 'add' ? 'Low' : dialog.riskLevel} />
                <Typography variant="caption" color="text.secondary">
                  {dialog.mode === 'add' ? 'New accounts start at Low. ' : ''}
                  Rule Detection raises it to Medium or High when the account's transactions match the fraud rules.
                </Typography>
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog({ ...dialog, open: false })}>Cancel</Button>
          <Button variant="contained" onClick={handleSave}>Save</Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirm.open} title="Deactivate account?"
        message={`Account ${confirm.uid} will be marked inactive. You can reactivate it later.`}
        confirmText="Deactivate" confirmColor="error"
        onConfirm={doDeactivate} onClose={() => setConfirm({ open: false, uid: null })}
      />
    </Box>
  )
}
