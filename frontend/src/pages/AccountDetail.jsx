import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert, Box, Breadcrumbs, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, Grid, LinearProgress, Link, MenuItem, Paper, Stack, Tab, Table, TableBody, TableCell,
  TableHead, TableRow, Tabs, TextField, Typography,
} from '@mui/material'
import GppBadIcon from '@mui/icons-material/GppBad'
import ManageSearchIcon from '@mui/icons-material/ManageSearch'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import MailOutlineIcon from '@mui/icons-material/MailOutline'
import RiskChip from '../components/RiskChip'
import FraudStatusChip from '../components/FraudStatusChip'
import { useAuth } from '../context/AuthContext'
import { isFraudAnalyst, useNotifications } from '../context/NotificationsContext'
import { getInvestigation, retryEmail, reviewAccount } from '../api/investigation'
import { eventTime, money, pct, txnTime } from '../utils/format'

const EMAIL_STATUS = {
  sent: { label: 'Sent', color: 'success' },
  pending: { label: 'Sending…', color: 'default' },
  failed: { label: 'Failed', color: 'error' },
  skipped: { label: 'Not sent', color: 'warning' },
}
const ACTIONS = {
  under_review: {
    title: 'Mark account as under review',
    button: 'Mark under review',
    noteLabel: 'Note (optional)',
    explain: 'Records that you are investigating this account. Nothing is sent to the account holder.',
  },
  confirm_fraud: {
    title: 'Confirm fraud and flag account',
    button: 'Confirm fraud & flag account',
    noteLabel: 'Evidence / reason (optional)',
    explain: 'Use this only after reviewing the evidence. It flags the account as Confirmed Fraud under your name, '
      + 'emails the account holder at their registered address (sent by the server), and alerts every fraud '
      + 'analyst in real time whenever this account makes another transaction. An ML score never does this on its own.',
  },
  clear: {
    title: 'Clear the review',
    button: 'Clear review',
    noteLabel: 'Reason (required)',
    explain: 'Removes the Under Review or Confirmed Fraud status. The history keeps a record of it and of your reason.',
  },
}
const MAX_EMAIL_POLLS = 30

function Field({ label, children }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{label}</Typography>
      <Box sx={{ fontSize: 14 }}>{children}</Box>
    </Box>
  )
}

function EmailRow({ email, onRetry, retrying }) {
  const status = EMAIL_STATUS[email.status] || EMAIL_STATUS.pending
  return (
    <Box sx={{ py: 1.25, borderTop: '1px solid', borderColor: 'divider' }}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" label={status.label} color={status.color}
            icon={email.status === 'pending' ? <CircularProgress size={12} /> : <MailOutlineIcon />} />
          <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{email.recipient || 'no address on file'}</Typography>
        </Stack>
        {(email.status === 'failed' || email.status === 'skipped') && (
          <Button size="small" startIcon={<RestartAltIcon />} onClick={() => onRetry(email)} disabled={retrying}>
            Retry
          </Button>
        )}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        {email.status === 'sent'
          ? `Delivered to the mail server ${eventTime(email.sent_at)}`
          : `Requested ${eventTime(email.created_at)} by ${email.requested_by || '—'} · ${email.attempts} attempt${email.attempts === 1 ? '' : 's'}`}
      </Typography>
      {email.last_error && email.status !== 'sent' && (
        <Typography variant="caption" color={email.status === 'failed' ? 'error.main' : 'warning.dark'}
          sx={{ display: 'block', overflowWrap: 'anywhere' }}>
          {email.last_error}
        </Typography>
      )}
    </Box>
  )
}

export default function AccountDetail() {
  const { uid } = useParams()
  const [params] = useSearchParams()
  const highlight = params.get('txn')
  const { user } = useAuth()
  const analyst = isFraudAnalyst(user)
  const notifications = useNotifications()

  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('transactions')
  const [dialog, setDialog] = useState(null)
  const [note, setNote] = useState('')
  const [txnChoice, setTxnChoice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [dialogError, setDialogError] = useState('')
  const [result, setResult] = useState(null)
  const [retrying, setRetrying] = useState(false)
  const polls = useRef(0)
  const highlightRow = useRef(null)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      setData(await getInvestigation(uid))
      setError('')
    } catch (err) {
      const status = err?.response?.status
      setError(status === 403 ? 'Investigating accounts needs a fraud analyst account.'
        : status === 404 ? `Account ${uid} was not found.`
          : 'Could not load this account. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [uid])

  useEffect(() => { load() }, [load])
  // a live notification (e.g. this account just made a transaction): refresh quietly
  useEffect(() => { if (notifications?.version) load(true) }, [notifications?.version, load])
  // the email is sent in the background after a confirmation: follow it until it settles
  const emailPending = data?.emails?.some((e) => e.status === 'pending')
  useEffect(() => {
    if (!emailPending) { polls.current = 0; return undefined }
    const timer = setInterval(() => {
      polls.current += 1
      if (polls.current > MAX_EMAIL_POLLS) clearInterval(timer)
      else load(true)
    }, 2000)
    return () => clearInterval(timer)
  }, [emailPending, load])
  useEffect(() => {
    if (highlight && highlightRow.current) highlightRow.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [highlight, data])

  const transactions = useMemo(() => data?.transactions || [], [data])
  const suspiciousFirst = useMemo(
    () => [...transactions].sort((a, b) => (b.status === 'suspicious') - (a.status === 'suspicious')),
    [transactions])

  function openDialog(action) {
    setNote(''); setDialogError('')
    const preferred = transactions.find((t) => t.txn_uid === highlight)
      || transactions.find((t) => t.status === 'suspicious')
    setTxnChoice(action === 'confirm_fraud' && preferred ? preferred.txn_uid : '')
    setDialog(action)
  }

  async function submit() {
    if (dialog === 'clear' && !note.trim()) { setDialogError('Give a reason for clearing the review.'); return }
    setSubmitting(true); setDialogError('')
    try {
      const res = await reviewAccount(uid, { action: dialog, note, transactionUid: txnChoice || null })
      setResult(res)
      setDialog(null)
      await load(true)
    } catch (err) {
      setDialogError(err?.response?.data?.detail || 'Could not update the account.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRetry(email) {
    setRetrying(true)
    try {
      await retryEmail(uid, email.id)
      await load(true)
    } catch (err) {
      setResult({ changed: false, message: err?.response?.data?.detail || 'Could not retry the email.', error: true })
    } finally {
      setRetrying(false)
    }
  }

  if (loading && !data) return <Box sx={{ pt: 4 }}><LinearProgress /></Box>
  if (error && !data) {
    return (
      <Box>
        <Breadcrumbs sx={{ mb: 2 }}><Link component={RouterLink} to="/accounts">Accounts</Link><Typography>{uid}</Typography></Breadcrumbs>
        <Alert severity={error.includes('analyst') ? 'warning' : 'error'}>{error}</Alert>
      </Box>
    )
  }

  const account = data.account
  const status = account.fraud_status
  const review = account.review_status
  const latestEmail = data.emails[0]

  return (
    <Box>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/accounts" underline="hover">Accounts</Link>
        <Typography color="text.primary">{account.account_uid}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }}
        spacing={2} sx={{ mb: 2 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h4">{account.customer_name}</Typography>
            <FraudStatusChip status={status} size="medium" />
          </Stack>
          <Typography variant="body2" color="text.secondary">
            <Box component="span" sx={{ fontFamily: 'monospace' }}>{account.account_uid}</Box>
            {' · '}{account.account_type || 'Account'}{account.is_active ? '' : ' · Inactive'}
          </Typography>
        </Box>
        {analyst && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {!review && (
              <Button variant="outlined" startIcon={<ManageSearchIcon />} onClick={() => openDialog('under_review')}>
                Mark under review
              </Button>
            )}
            {review !== 'Confirmed Fraud' && (
              <Button variant="contained" color="error" startIcon={<GppBadIcon />} onClick={() => openDialog('confirm_fraud')}>
                Confirm fraud &amp; flag account
              </Button>
            )}
            {review && (
              <Button variant="outlined" color="inherit" startIcon={<RestartAltIcon />} onClick={() => openDialog('clear')}>
                Clear review
              </Button>
            )}
          </Stack>
        )}
      </Stack>

      {result && (
        <Alert severity={result.error ? 'error' : result.changed ? 'success' : 'info'} sx={{ mb: 2 }}
          onClose={() => setResult(null)}>
          {result.message}
          {result.changed && result.email && ' The account holder email is being handled separately — see its status below.'}
        </Alert>
      )}
      {loading && <LinearProgress sx={{ mb: 1 }} />}

      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>Fraud status</Typography>
            <Field label="Status"><FraudStatusChip status={status} /></Field>
            {review === 'Confirmed Fraud' && (
              <Field label="Confirmed by">{account.fraud_confirmed_by} · {eventTime(account.fraud_confirmed_at)}</Field>
            )}
            <Field label="Rule-based risk level"><RiskChip level={account.risk_level} /></Field>
            <Field label="ML fraud score">{pct(account.fraud_score)}</Field>
            <Typography variant="caption" color="text.secondary">
              Suspicious comes from the rules (Medium/High risk) or an ML score of 80% or more and needs an analyst's
              review. Only an analyst's confirmation makes an account Confirmed Fraud.
            </Typography>
          </Paper>

          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>Account holder</Typography>
            <Field label="Email">{account.email || '—'}</Field>
            <Field label="Phone">{account.phone || '—'}</Field>
            <Field label="Opened">{txnTime(account.created_at)}</Field>
          </Paper>

          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 0.5 }}>Account holder email</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Sent by the server when an analyst confirms fraud — never for ML predictions alone.
            </Typography>
            {data.emails.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No email has been sent for this account.</Typography>
            ) : data.emails.map((e) => (
              <EmailRow key={e.id} email={e} onRetry={handleRetry} retrying={retrying} />
            ))}
          </Paper>

          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Investigation history</Typography>
            {data.status_history.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No analyst has reviewed this account yet.</Typography>
            ) : data.status_history.map((e) => (
              <Box key={e.id} sx={{ py: 1.25, borderTop: '1px solid', borderColor: 'divider' }}>
                <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                  <FraudStatusChip status={e.from_status || 'Normal'} />
                  <Typography variant="body2" color="text.secondary">→</Typography>
                  {e.to_status ? <FraudStatusChip status={e.to_status} /> : <Chip size="small" label="Review cleared" variant="outlined" />}
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  {e.changed_by} · {eventTime(e.created_at)}
                  {e.transaction_uid && <> · re <Box component="span" sx={{ fontFamily: 'monospace' }}>{e.transaction_uid}</Box></>}
                </Typography>
                {e.note && <Typography variant="body2" sx={{ mt: 0.5 }}>{e.note}</Typography>}
              </Box>
            ))}
          </Paper>
        </Grid>

        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2 }}>
            <Tabs value={tab} onChange={(e, v) => setTab(v)} sx={{ mb: 1 }} variant="scrollable">
              <Tab value="transactions" label={`Transactions (${data.transaction_count.toLocaleString('en-IN')})`} />
              <Tab value="alerts" label={`Alerts (${data.alerts.length})`} />
              <Tab value="cases" label={`Cases (${data.cases.length})`} />
              <Tab value="notifications" label={`Notifications (${data.notifications.length})`} />
            </Tabs>

            {tab === 'transactions' && (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Txn UID</TableCell><TableCell>Direction</TableCell><TableCell>Counterparty</TableCell>
                      <TableCell align="right">Amount</TableCell><TableCell>Time</TableCell><TableCell>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {transactions.map((t) => {
                      const sent = t.sender_uid === account.account_uid
                      const other = sent ? t.receiver_uid : t.sender_uid
                      const isHighlight = t.txn_uid === highlight
                      return (
                        <TableRow key={t.txn_uid} ref={isHighlight ? highlightRow : null} hover
                          sx={isHighlight ? { bgcolor: 'rgba(220,38,38,0.08)', '& td': { fontWeight: 600 } } : undefined}>
                          <TableCell sx={{ fontFamily: 'monospace' }}>{t.txn_uid}</TableCell>
                          <TableCell>{sent ? 'Sent' : 'Received'}</TableCell>
                          <TableCell>
                            <Link component={RouterLink} to={`/accounts/${encodeURIComponent(other)}`} sx={{ fontFamily: 'monospace' }}>{other}</Link>
                          </TableCell>
                          <TableCell align="right">{money(t.amount)}</TableCell>
                          <TableCell>{txnTime(t.timestamp)}</TableCell>
                          <TableCell>
                            <Chip size="small" label={t.status} variant="outlined"
                              color={t.status === 'suspicious' ? 'warning' : 'default'} />
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {transactions.length === 0 && (
                      <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>No transactions</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
                {data.transaction_count > transactions.length && (
                  <Typography variant="caption" color="text.secondary">
                    Showing the latest {transactions.length} of {data.transaction_count.toLocaleString('en-IN')} transactions.
                  </Typography>
                )}
              </Box>
            )}

            {tab === 'alerts' && (
              <Table size="small">
                <TableHead>
                  <TableRow><TableCell>Alert</TableCell><TableCell>Target</TableCell><TableCell>Reason</TableCell>
                    <TableCell>Risk</TableCell><TableCell>Status</TableCell><TableCell>Created</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {data.alerts.map((a) => (
                    <TableRow key={a.alert_uid} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{a.alert_uid}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{a.transaction_uid || a.account_uid}</TableCell>
                      <TableCell sx={{ maxWidth: 280 }}><Typography variant="body2" noWrap title={a.reason}>{a.reason}</Typography></TableCell>
                      <TableCell><RiskChip level={a.risk_level} /></TableCell>
                      <TableCell>{a.status}</TableCell>
                      <TableCell>{eventTime(a.created_at)}</TableCell>
                    </TableRow>
                  ))}
                  {data.alerts.length === 0 && (
                    <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>No alerts</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            )}

            {tab === 'cases' && (
              <Table size="small">
                <TableHead>
                  <TableRow><TableCell>Case</TableCell><TableCell>Assigned to</TableCell><TableCell>Status</TableCell>
                    <TableCell>Final decision</TableCell><TableCell>Created</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {data.cases.map((c) => (
                    <TableRow key={c.case_uid} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>
                        <Link component={RouterLink} to="/cases">{c.case_uid}</Link>
                      </TableCell>
                      <TableCell>{c.assigned_to || '—'}</TableCell>
                      <TableCell>{c.status}</TableCell>
                      <TableCell>{c.final_decision || '—'}</TableCell>
                      <TableCell>{eventTime(c.created_at)}</TableCell>
                    </TableRow>
                  ))}
                  {data.cases.length === 0 && (
                    <TableRow><TableCell colSpan={5} align="center" sx={{ py: 3, color: 'text.secondary' }}>No investigation cases</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            )}

            {tab === 'notifications' && (
              <Table size="small">
                <TableHead>
                  <TableRow><TableCell>When</TableCell><TableCell>Transaction</TableCell>
                    <TableCell align="right">Amount</TableCell><TableCell>Alert</TableCell><TableCell>Read</TableCell></TableRow>
                </TableHead>
                <TableBody>
                  {data.notifications.map((n) => (
                    <TableRow key={n.id} hover>
                      <TableCell>{eventTime(n.created_at)}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{n.transaction_uid}</TableCell>
                      <TableCell align="right">{money(n.amount)}</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{n.alert_uid}</TableCell>
                      <TableCell>{n.read ? 'Read' : <Chip size="small" color="error" label="Unread" />}</TableCell>
                    </TableRow>
                  ))}
                  {data.notifications.length === 0 && (
                    <TableRow><TableCell colSpan={5} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                      No notifications. They appear when an account confirmed as fraud makes a new transaction.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </Paper>
          {latestEmail && review === 'Confirmed Fraud' && latestEmail.status !== 'sent' && (
            <Alert severity={latestEmail.status === 'pending' ? 'info' : 'warning'} sx={{ mt: 2 }}>
              The account is flagged. The account holder email {latestEmail.status === 'pending'
                ? 'is being sent.' : 'was not delivered yet — see "Account holder email" for the reason and to retry.'}
            </Alert>
          )}
        </Grid>
      </Grid>

      <Dialog open={!!dialog} onClose={() => !submitting && setDialog(null)} fullWidth maxWidth="sm">
        {dialog && (
          <>
            <DialogTitle>{ACTIONS[dialog].title}</DialogTitle>
            <DialogContent>
              <Alert severity={dialog === 'confirm_fraud' ? 'warning' : 'info'} sx={{ mb: 2 }}>{ACTIONS[dialog].explain}</Alert>
              {dialogError && <Alert severity="error" sx={{ mb: 2 }}>{dialogError}</Alert>}
              <Stack spacing={2}>
                {dialog === 'confirm_fraud' && (
                  <TextField select label="Related transaction" value={txnChoice}
                    onChange={(e) => setTxnChoice(e.target.value)}
                    helperText="Quoted in the email to the account holder (reference, date and amount).">
                    <MenuItem value="">None</MenuItem>
                    {suspiciousFirst.slice(0, 50).map((t) => (
                      <MenuItem key={t.txn_uid} value={t.txn_uid}>
                        {t.txn_uid} · {money(t.amount)} · {txnTime(t.timestamp)}{t.status === 'suspicious' ? ' · suspicious' : ''}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
                <TextField label={ACTIONS[dialog].noteLabel} value={note} multiline minRows={3}
                  onChange={(e) => setNote(e.target.value)} inputProps={{ maxLength: 2000 }}
                  required={dialog === 'clear'} />
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDialog(null)} disabled={submitting}>Cancel</Button>
              <Button variant="contained" color={dialog === 'confirm_fraud' ? 'error' : 'primary'}
                onClick={submit} disabled={submitting}>
                {submitting ? 'Saving…' : ACTIONS[dialog].button}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  )
}
