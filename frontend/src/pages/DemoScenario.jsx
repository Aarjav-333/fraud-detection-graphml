import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import {
  Alert, AlertTitle, Box, Button, Chip, Grid, LinearProgress, Link, MenuItem, Paper, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Tooltip, Typography,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import RefreshIcon from '@mui/icons-material/Refresh'
import ScienceIcon from '@mui/icons-material/Science'
import SendIcon from '@mui/icons-material/Send'
import RiskChip from '../components/RiskChip'
import FraudStatusChip from '../components/FraudStatusChip'
import MoneyFlowGraph from '../components/MoneyFlowGraph'
import { getDemoScenario } from '../api/demo'
import { createTransaction } from '../api/transactions'
import { useNotifications } from '../context/NotificationsContext'
import { useSystem } from '../context/SystemContext'
import { money, txnTime } from '../utils/format'

// Three groups, validated for a network where any two nodes can sit side by side
// (dark surface, all pairs); each node also carries its own label.
const GROUP = {
  feeder: { label: 'Feeders (sources)', color: '#3987e5' },
  core: { label: 'Mule · collector · shells', color: '#d95926' },
  'cash-out': { label: 'Cash-out accounts', color: '#199e70' },
}
const groupOf = (role) => (role === 'feeder' || role === 'cash-out' ? role : 'core')
const RADIUS = { collector: 11, mule: 9, shell: 7, feeder: 5, 'cash-out': 5 }
const ROLE_LABEL = { feeder: 'Feeder', mule: 'Mule', collector: 'Collector', shell: 'Shell', 'cash-out': 'Cash-out' }
const short = (uid) => uid.replace(/^DEMO-/, '')
const newKey = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`

function Tile({ value, label, sub }) {
  return (
    <Paper sx={{ p: 2, height: '100%' }}>
      <Typography variant="h5">{value}</Typography>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      {sub && <Box sx={{ mt: 0.75 }}>{sub}</Box>}
    </Paper>
  )
}

function RuleChip({ code, labels, fired = true, count }) {
  return (
    <Tooltip title={labels[code] || code}>
      <Chip size="small" label={count ? `${code} ×${count}` : code} color="primary"
        variant={fired ? 'filled' : 'outlined'} sx={{ mr: 0.5, mb: 0.5 }} />
    </Tooltip>
  )
}

function AccountLink({ uid, role }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: GROUP[groupOf(role)].color, flexShrink: 0 }} />
      <Link component={RouterLink} to={`/accounts/${encodeURIComponent(uid)}`} underline="hover"
        sx={{ fontFamily: 'monospace', fontSize: 13 }}>{uid}</Link>
      <Typography variant="caption" color="text.secondary">{ROLE_LABEL[role]}</Typography>
    </Stack>
  )
}

function StageCard({ stage, labels }) {
  return (
    <Paper sx={{ p: 2.5, mb: 2 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1} sx={{ mb: 1 }}>
        <Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h6">Stage {stage.number} · {stage.name}</Typography>
            {stage.detected
              ? <Chip size="small" color="success" icon={<CheckCircleIcon />} label="Detected" />
              : <Chip size="small" variant="outlined" icon={<HourglassEmptyIcon />} label="Not detected yet" />}
          </Stack>
          <Typography variant="body2" color="text.secondary">{stage.description}</Typography>
        </Box>
        <Box sx={{ textAlign: { md: 'right' }, flexShrink: 0 }}>
          <Typography variant="body2"><b>{stage.flagged}/{stage.total}</b> transactions flagged · {money(stage.amount)}</Typography>
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mr: 0.75 }}>Designed to trigger</Typography>
            {stage.expected_rules.map((code) => (
              <RuleChip key={code} code={code} labels={labels} fired={!!stage.rules_fired[code]} count={stage.rules_fired[code]} />
            ))}
          </Box>
        </Box>
      </Stack>
      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Transaction</TableCell><TableCell>From</TableCell><TableCell>To</TableCell>
              <TableCell align="right">Amount</TableCell><TableCell>Time</TableCell>
              <TableCell>Rules fired</TableCell><TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {stage.transactions.map((t) => (
              <TableRow key={t.txn_uid} hover>
                <TableCell sx={{ fontFamily: 'monospace' }}>
                  <Tooltip title="Open the sending account at this transaction">
                    <Link component={RouterLink} underline="hover"
                      to={`/accounts/${encodeURIComponent(t.sender_uid)}?txn=${encodeURIComponent(t.txn_uid)}`}>
                      {t.txn_uid}
                    </Link>
                  </Tooltip>
                </TableCell>
                <TableCell><AccountLink uid={t.sender_uid} role={t.sender_role} /></TableCell>
                <TableCell><AccountLink uid={t.receiver_uid} role={t.receiver_role} /></TableCell>
                <TableCell align="right">{money(t.amount)}</TableCell>
                <TableCell>{txnTime(t.timestamp)}</TableCell>
                <TableCell>
                  {t.rules.length ? t.rules.map((code) => <RuleChip key={code} code={code} labels={labels} />)
                    : <Typography variant="caption" color="text.secondary">none</Typography>}
                </TableCell>
                <TableCell>
                  <Chip size="small" variant="outlined" label={t.status}
                    color={t.status === 'suspicious' ? 'warning' : 'default'} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Paper>
  )
}

function RealTimeTest({ accounts, onRecorded }) {
  const [sender, setSender] = useState('DEMO-COLLECTOR')
  const [receiver, setReceiver] = useState('DEMO-CASH01')
  const [amount, setAmount] = useState('25000')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const senderAccount = accounts.find((a) => a.account_uid === sender)
  const confirmed = senderAccount?.fraud_status === 'Confirmed Fraud'

  function pickSender(uid) {
    setSender(uid)
    if (uid === receiver) {   // it can't pay itself: move the receiver on to another account
      setReceiver(accounts.find((a) => a.account_uid !== uid)?.account_uid || '')
    }
  }

  async function record() {
    setBusy(true); setResult(null)
    try {
      const txn = await createTransaction(
        { sender_uid: sender, receiver_uid: receiver, amount: parseFloat(amount), txn_type: 'transfer' }, newKey())
      setResult({ ok: true, text: `Recorded ${txn.txn_uid}.${confirmed ? ' Watch the bell: the alert arrives without a refresh.' : ''}` })
      onRecorded()
    } catch (err) {
      setResult({ ok: false, text: err?.response?.data?.detail || 'Could not record the transaction.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper sx={{ p: 2.5, height: '100%' }}>
      <Typography variant="h6">Try the real-time alert</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        1. Open an account (e.g. <Link component={RouterLink} to="/accounts/DEMO-COLLECTOR">DEMO-COLLECTOR</Link>) and
        click <b>Confirm fraud &amp; flag account</b>. 2. Record a new transaction from it here (or on the Transactions
        page). Every fraud analyst gets a High-priority alert as it is recorded.
      </Typography>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1.5}>
          <TextField select size="small" label="From" value={sender} onChange={(e) => pickSender(e.target.value)} sx={{ flex: 1 }}>
            {accounts.map((a) => <MenuItem key={a.account_uid} value={a.account_uid}>{a.account_uid} · {ROLE_LABEL[a.role]}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="To" value={receiver} onChange={(e) => setReceiver(e.target.value)} sx={{ flex: 1 }}>
            {accounts.filter((a) => a.account_uid !== sender).map((a) => (
              <MenuItem key={a.account_uid} value={a.account_uid}>{a.account_uid} · {ROLE_LABEL[a.role]}</MenuItem>
            ))}
          </TextField>
        </Stack>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <TextField size="small" label="Amount (₹)" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} sx={{ width: 160 }} />
          <Button variant="contained" startIcon={<SendIcon />} onClick={record}
            disabled={busy || !(parseFloat(amount) > 0) || !receiver || sender === receiver}>
            {busy ? 'Recording…' : 'Record transaction'}
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption" color="text.secondary">{sender} is</Typography>
          <FraudStatusChip status={senderAccount?.fraud_status} />
          {!confirmed && <Typography variant="caption" color="text.secondary">— confirm it first, or no alert is raised.</Typography>}
        </Stack>
        {result && <Alert severity={result.ok ? 'success' : 'error'} onClose={() => setResult(null)}>{result.text}</Alert>}
      </Stack>
    </Paper>
  )
}

export default function DemoScenario() {
  const { standalone, mlUnavailableReason } = useSystem()
  const live = useNotifications()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const latest = useRef(0)

  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    try {
      const next = await getDemoScenario()
      if (request !== latest.current) return   // a newer load is on its way
      setData(next)
      setError('')
    } catch (err) {
      if (request !== latest.current) return
      setError(err?.response?.status === 404
        ? 'The demo scenario isn\'t in this database.'
        : 'Could not load the demo scenario. Is the backend running?')
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [])

  // On arrival, and again whenever a review or alert changes something
  const version = live?.version
  useEffect(() => { load() }, [load, version])

  const labels = data?.rule_labels || {}
  const graph = useMemo(() => data?.graph, [data])

  if (!data) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 2 }}>Demo Scenario</Typography>
        {loading ? <LinearProgress /> : (
          <Alert severity={error.startsWith('The demo') ? 'info' : 'error'}>
            {error} Build the standalone demo with{' '}
            <Box component="code" sx={{ fontFamily: 'monospace' }}>python -m scripts.demo_scenario --standalone</Box>,
            then serve it with{' '}
            <Box component="code" sx={{ fontFamily: 'monospace' }}>--serve --standalone</Box>.
          </Alert>
        )}
      </Box>
    )
  }

  const cov = data.coverage
  const pipeline = data.pipeline
  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h4">Demo Scenario</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            A scripted mule-network laundering operation in four stages — what the detection pipeline caught
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} onClick={load} disabled={loading}>Refresh</Button>
      </Stack>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {error && (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error} Showing what was last loaded.
        </Alert>
      )}

      {!pipeline.rules_run && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <AlertTitle>Detection hasn't run yet</AlertTitle>
          Run the steps from the sidebar, in order: <Link component={RouterLink} to="/rules">Rule Detection</Link> →{' '}
          <Link component={RouterLink} to="/graph">Graph Analysis</Link> → <Link component={RouterLink} to="/features">Features</Link> →{' '}
          <Link component={RouterLink} to="/alerts">Fraud Alerts</Link> → <Link component={RouterLink} to="/rings">Fraud Rings</Link>.
          This page then shows what each stage triggered.
        </Alert>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <Tile value={`${cov.transactions_flagged}/${cov.transactions_total}`} label="Scripted transactions flagged" />
        </Grid>
        <Grid item xs={6} md={3}>
          <Tile value={`${cov.stages_detected}/${cov.stages_total}`} label="Stages detected" />
        </Grid>
        <Grid item xs={6} md={3}>
          <Tile value={`${cov.rules_fired.length}/${cov.rules_expected.length}`} label="Rules fired"
            sub={cov.rules_expected.map((code) => (
              <RuleChip key={code} code={code} labels={labels} fired={cov.rules_fired.includes(code)} />
            ))} />
        </Grid>
        <Grid item xs={6} md={3}>
          <Tile value={`${cov.accounts_in_rings}/${cov.accounts_total}`} label="Accounts in a detected fraud ring"
            sub={<Typography variant="caption" color="text.secondary">
              This database: {data.database.accounts.toLocaleString('en-IN')} accounts,{' '}
              {data.database.transactions.toLocaleString('en-IN')} transactions
            </Typography>} />
        </Grid>
      </Grid>

      {data.stages.map((stage) => <StageCard key={stage.stage} stage={stage} labels={labels} />)}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} lg={7}>
          <Paper sx={{ p: 2.5, height: '100%' }}>
            <Typography variant="h6">The fraud network</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Every account in the scenario and the money between them. Hover a node or an edge for details.
            </Typography>
            <MoneyFlowGraph
              nodes={graph.nodes} links={graph.links} height={420}
              colorOf={(n) => GROUP[groupOf(n.role)].color}
              radiusOf={(n) => RADIUS[n.role] || 5}
              labelOf={(n) => short(n.id)}
              nodeTitle={(n) => `${n.id} · ${n.name}\nrole: ${ROLE_LABEL[n.role]} · risk ${n.risk_level || '—'} · ${n.fraud_status || ''}`}
              legend={Object.values(GROUP)}
            />
          </Paper>
        </Grid>
        <Grid item xs={12} lg={5}>
          <Stack spacing={2} sx={{ height: '100%' }}>
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>Detected fraud rings</Typography>
              {data.rings.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {pipeline.rings_run ? 'No ring contains the scenario.' : 'Ring detection hasn\'t run yet.'}
                </Typography>
              ) : data.rings.map((ring) => (
                <Box key={ring.ring_id} sx={{ py: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{ring.ring_id}</Typography>
                    <RiskChip level={ring.risk} />
                  </Stack>
                  <Typography variant="body2">
                    {ring.size} accounts{ring.other_members ? ` (${ring.scenario_members} from the scenario)` : ', all from the scenario'} ·
                    main <b>{ring.main_account}</b> · withdrawal <b>{ring.withdrawal_account || '—'}</b> · {money(ring.total_flow)} moved
                  </Typography>
                  <Box sx={{ mt: 0.5 }}>
                    {ring.rules.map((code) => <RuleChip key={code} code={code} labels={labels} />)}
                  </Box>
                  <Button size="small" sx={{ mt: 0.5 }} onClick={() => navigate('/rings')}>View on Fraud Rings</Button>
                </Box>
              ))}
            </Paper>
            <RealTimeTest accounts={data.accounts} onRecorded={load} />
          </Stack>
        </Grid>
      </Grid>

      <Paper sx={{ p: 2.5, mb: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>Accounts</Typography>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Account</TableCell><TableCell>Name</TableCell><TableCell>Risk (rules)</TableCell>
                <TableCell>Fraud status</TableCell><TableCell align="right">Alerts</TableCell><TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {data.accounts.map((a) => (
                <TableRow key={a.account_uid} hover>
                  <TableCell><AccountLink uid={a.account_uid} role={a.role} /></TableCell>
                  <TableCell>{a.customer_name}</TableCell>
                  <TableCell><RiskChip level={a.risk_level} /></TableCell>
                  <TableCell><FraudStatusChip status={a.fraud_status} /></TableCell>
                  <TableCell align="right">{a.alerts}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => navigate(`/accounts/${encodeURIComponent(a.account_uid)}`)}>Investigate</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      {data.other_transactions.count > 0 && (
        <Paper sx={{ p: 2.5, mb: 2 }}>
          <Typography variant="h6">Transactions after the scenario ({data.other_transactions.count})</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Recorded since the scenario was planted{data.other_transactions.count > data.other_transactions.recent.length ? ' (latest shown)' : ''}.
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow><TableCell>Transaction</TableCell><TableCell>From</TableCell><TableCell>To</TableCell>
                <TableCell align="right">Amount</TableCell><TableCell>Status</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {data.other_transactions.recent.map((t) => (
                <TableRow key={t.txn_uid} hover>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{t.txn_uid}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{t.sender_uid}</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>{t.receiver_uid}</TableCell>
                  <TableCell align="right">{money(t.amount)}</TableCell>
                  <TableCell>{t.status}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {standalone && (
        <Alert severity="info" icon={<ScienceIcon />}>
          <AlertTitle>Why there are no model scores here</AlertTitle>
          {mlUnavailableReason}
        </Alert>
      )}
    </Box>
  )
}
