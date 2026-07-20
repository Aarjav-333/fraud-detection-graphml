import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Box, Typography, Paper, Table, TableHead, TableBody, TableRow, TableCell,
  TablePagination, TextField, Button, IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, Stack, MenuItem, Chip, InputAdornment, Tooltip, CircularProgress,
  Alert, FormControlLabel, Switch, List, ListItem, ListItemText, Snackbar,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import DeleteIcon from '@mui/icons-material/Delete'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import ConfirmDialog from '../components/ConfirmDialog'
import {
  listTransactions, createTransaction, deleteTransaction, uploadTransactionsCSV,
} from '../api/transactions'

const TXN_TYPES = ['transfer', 'payment', 'withdrawal']
const EMPTY = { sender_uid: '', receiver_uid: '', amount: '', txn_type: 'transfer' }
const money = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })

export default function Transactions() {
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [fraudOnly, setFraudOnly] = useState(false)
  const [loading, setLoading] = useState(false)

  const [addOpen, setAddOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [confirm, setConfirm] = useState({ open: false, uid: null })
  const [uploadResult, setUploadResult] = useState(null)
  const [toast, setToast] = useState('')
  const fileRef = useRef(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listTransactions({ skip: page * rowsPerPage, limit: rowsPerPage, q, fraudOnly })
      setRows(data.items)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, q, fraudOnly])

  useEffect(() => { fetchData() }, [fetchData])
  useEffect(() => {
    const t = setTimeout(() => { setPage(0); setQ(search) }, 400)
    return () => clearTimeout(t)
  }, [search])

  function openAdd() { setForm(EMPTY); setFormError(''); setAddOpen(true) }

  async function handleCreate() {
    setFormError('')
    if (!form.sender_uid || !form.receiver_uid || !form.amount) {
      setFormError('Sender, receiver and amount are required'); return
    }
    try {
      await createTransaction({ ...form, amount: parseFloat(form.amount) })
      setAddOpen(false)
      setToast('Transaction added')
      fetchData()
    } catch (err) {
      setFormError(err?.response?.data?.detail || 'Could not create transaction')
    }
  }

  async function doDelete() {
    await deleteTransaction(confirm.uid)
    setConfirm({ open: false, uid: null })
    setToast('Transaction deleted')
    fetchData()
  }

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await uploadTransactionsCSV(file)
      setUploadResult(result)
      fetchData()
    } catch (err) {
      setUploadResult({ inserted: 0, skipped: 0, errors: [err?.response?.data?.detail || 'Upload failed'] })
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Transactions</Typography>
          <Typography variant="body2" color="text.secondary">
            {total.toLocaleString('en-IN')} transactions{fraudOnly ? ' (fraud only)' : ''}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<UploadFileIcon />} onClick={() => fileRef.current?.click()}>
            Upload CSV
          </Button>
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={handleFile} />
          <Button variant="contained" startIcon={<AddIcon />} onClick={openAdd}>Add transaction</Button>
        </Stack>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <TextField
            size="small" placeholder="Search by txn ID, sender or receiver…" value={search}
            onChange={(e) => setSearch(e.target.value)} sx={{ width: 360 }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          />
          <FormControlLabel
            control={<Switch checked={fraudOnly} onChange={(e) => { setPage(0); setFraudOnly(e.target.checked) }} />}
            label="Fraud only (ground truth)"
          />
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
                <TableCell>Txn UID</TableCell>
                <TableCell>Sender</TableCell>
                <TableCell>Receiver</TableCell>
                <TableCell align="right">Amount</TableCell>
                <TableCell>Time</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Label</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.txn_uid} hover>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{r.txn_uid}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{r.sender_uid}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{r.receiver_uid}</TableCell>
                  <TableCell align="right">{money(r.amount)}</TableCell>
                  <TableCell>{new Date(r.timestamp).toLocaleString('en-IN')}</TableCell>
                  <TableCell>{r.txn_type}</TableCell>
                  <TableCell>
                    <Chip size="small" label={r.status}
                      color={r.status === 'suspicious' ? 'warning' : 'default'} variant="outlined" />
                  </TableCell>
                  <TableCell>
                    {r.is_fraud
                      ? <Chip size="small" label="Fraud" color="error" />
                      : <Chip size="small" label="Legit" variant="outlined" />}
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Delete">
                      <IconButton size="small" onClick={() => setConfirm({ open: true, uid: r.txn_uid })}>
                        <DeleteIcon fontSize="small" color="error" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>No transactions found</TableCell></TableRow>
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

      {/* Add transaction dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add transaction</DialogTitle>
        <DialogContent>
          {formError && <Alert severity="error" sx={{ mb: 2 }}>{formError}</Alert>}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Sender account UID" value={form.sender_uid}
              onChange={(e) => setForm({ ...form, sender_uid: e.target.value })} placeholder="ACC00001" />
            <TextField label="Receiver account UID" value={form.receiver_uid}
              onChange={(e) => setForm({ ...form, receiver_uid: e.target.value })} placeholder="ACC00002" />
            <TextField label="Amount (₹)" type="number" value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            <TextField select label="Type" value={form.txn_type}
              onChange={(e) => setForm({ ...form, txn_type: e.target.value })}>
              {TXN_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}>Save</Button>
        </DialogActions>
      </Dialog>

      {/* CSV upload result */}
      <Dialog open={!!uploadResult} onClose={() => setUploadResult(null)} fullWidth maxWidth="sm">
        <DialogTitle>CSV upload result</DialogTitle>
        <DialogContent>
          {uploadResult && (
            <>
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <Chip color="success" label={`${uploadResult.inserted} inserted`} />
                <Chip color="warning" label={`${uploadResult.skipped} skipped`} variant="outlined" />
              </Stack>
              {uploadResult.errors?.length > 0 && (
                <>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Issues:</Typography>
                  <List dense>
                    {uploadResult.errors.map((e, i) => (
                      <ListItem key={i} sx={{ py: 0 }}><ListItemText primaryTypographyProps={{ variant: 'body2' }} primary={e} /></ListItem>
                    ))}
                  </List>
                </>
              )}
              <Alert severity="info" sx={{ mt: 1 }}>
                CSV needs columns: <b>sender_uid, receiver_uid, amount</b> (optional: timestamp, txn_type).
              </Alert>
            </>
          )}
        </DialogContent>
        <DialogActions><Button onClick={() => setUploadResult(null)}>Close</Button></DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirm.open} title="Delete transaction?"
        message={`Transaction ${confirm.uid} will be permanently removed.`}
        confirmText="Delete" confirmColor="error"
        onConfirm={doDelete} onClose={() => setConfirm({ open: false, uid: null })}
      />

      <Snackbar open={!!toast} autoHideDuration={2500} onClose={() => setToast('')} message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  )
}
