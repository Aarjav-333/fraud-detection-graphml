import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Table, TableHead, TableBody, TableRow, TableCell,
  TablePagination, TextField, Button, IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, Stack, MenuItem, Chip, InputAdornment, Tooltip, CircularProgress, Alert,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import EditIcon from '@mui/icons-material/Edit'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RiskChip from '../components/RiskChip'
import ConfirmDialog from '../components/ConfirmDialog'
import {
  listAccounts, createAccount, updateAccount, deactivateAccount, activateAccount,
} from '../api/accounts'

const ACCOUNT_TYPES = ['Savings', 'Current', 'Wallet', 'Business']
const RISK_LEVELS = ['Low', 'Medium', 'High']
const EMPTY = { customer_name: '', email: '', phone: '', account_type: 'Savings', risk_level: 'Low' }

export default function Accounts() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)

  const [dialog, setDialog] = useState({ open: false, mode: 'add', uid: null })
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [confirm, setConfirm] = useState({ open: false, uid: null })

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listAccounts({ skip: page * rowsPerPage, limit: rowsPerPage, q })
      setRows(data.items)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, q])

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
      account_type: row.account_type || 'Savings', risk_level: row.risk_level || 'Low',
    })
    setFormError('')
    setDialog({ open: true, mode: 'edit', uid: row.account_uid })
  }

  async function handleSave() {
    setFormError('')
    if (!form.customer_name.trim()) { setFormError('Customer name is required'); return }
    try {
      if (dialog.mode === 'add') await createAccount(form)
      else await updateAccount(dialog.uid, form)
      setDialog({ open: false, mode: 'add', uid: null })
      fetchData()
    } catch (err) {
      setFormError(err?.response?.data?.detail || 'Could not save account')
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
        <TextField
          size="small" placeholder="Search by name, UID or email…" value={search}
          onChange={(e) => setSearch(e.target.value)} sx={{ mb: 2, width: 340 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
        />
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
                <TableCell>Risk</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.account_uid} hover>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{r.account_uid}</TableCell>
                  <TableCell>{r.customer_name}</TableCell>
                  <TableCell>{r.email}</TableCell>
                  <TableCell>{r.phone}</TableCell>
                  <TableCell>{r.account_type}</TableCell>
                  <TableCell><RiskChip level={r.risk_level} /></TableCell>
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
                <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>No accounts found</TableCell></TableRow>
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
            <TextField select label="Risk level" value={form.risk_level}
              onChange={(e) => setForm({ ...form, risk_level: e.target.value })}>
              {RISK_LEVELS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </TextField>
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
