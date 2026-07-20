import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, Grid, Stack, Chip, LinearProgress, Alert, Table,
  TableHead, TableBody, TableRow, TableCell, Button,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import FolderSharedIcon from '@mui/icons-material/FolderShared'
import GroupsIcon from '@mui/icons-material/Groups'
import ModelTrainingIcon from '@mui/icons-material/ModelTraining'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, BarChart, Bar, Legend,
} from 'recharts'
import RiskChip from '../components/RiskChip'
import { getDashboardStats } from '../api/dashboard'

const money = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
const RISK_COLORS = { High: '#dc2626', Medium: '#d97706', Low: '#16a34a' }
const STATUS_COLORS = {
  'Pending': '#94a3b8', 'Under Review': '#0ea5e9',
  'Confirmed Fraud': '#dc2626', 'False Positive': '#d97706', 'Resolved': '#16a34a',
}

function StatCard({ icon, label, value, sub, color = 'primary.main', onClick }) {
  return (
    <Paper sx={{ p: 2, cursor: onClick ? 'pointer' : 'default', height: '100%' }} onClick={onClick}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Box sx={{ color, display: 'flex' }}>{icon}</Box>
        <Box>
          <Typography variant="h5" sx={{ lineHeight: 1.2 }}>{value}</Typography>
          <Typography variant="caption" color="text.secondary">{label}</Typography>
          {sub && <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{sub}</Typography>}
        </Box>
      </Stack>
    </Paper>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getDashboardStats().then(setStats)
      .catch(() => setError('Could not load dashboard — is the backend running?'))
  }, [])

  if (error) return <Alert severity="error">{error}</Alert>
  if (!stats) return <Box sx={{ pt: 4 }}><LinearProgress /></Box>

  const riskData = [
    { name: 'High', value: stats.accounts.high_risk },
    { name: 'Medium', value: stats.accounts.medium_risk },
    { name: 'Low', value: stats.accounts.low_risk },
  ]
  const alertData = Object.entries(stats.alerts.by_status || {})
    .map(([name, value]) => ({ name, value }))

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 0.5 }}>Dashboard</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Financial Fraud Detection with Graph ML — system overview
      </Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} md={2}>
          <StatCard icon={<AccountBalanceWalletIcon />} label="Accounts"
            value={stats.accounts.total.toLocaleString('en-IN')}
            sub={`${stats.accounts.high_risk} high risk`} onClick={() => navigate('/accounts')} />
        </Grid>
        <Grid item xs={6} md={2}>
          <StatCard icon={<SwapHorizIcon />} label="Transactions"
            value={stats.transactions.total.toLocaleString('en-IN')}
            sub={`${stats.transactions.suspicious.toLocaleString('en-IN')} suspicious`}
            onClick={() => navigate('/transactions')} />
        </Grid>
        <Grid item xs={6} md={2}>
          <StatCard icon={<WarningAmberIcon />} label="Alerts" color="error.main"
            value={stats.alerts.total.toLocaleString('en-IN')}
            sub={`${stats.alerts.by_status?.Pending ?? 0} pending`} onClick={() => navigate('/alerts')} />
        </Grid>
        <Grid item xs={6} md={2}>
          <StatCard icon={<FolderSharedIcon />} label="Open cases" color="warning.main"
            value={stats.cases.open.toLocaleString('en-IN')}
            sub={`${stats.cases.total} total`} onClick={() => navigate('/cases')} />
        </Grid>
        <Grid item xs={6} md={2}>
          <StatCard icon={<GroupsIcon />} label="Fraud rings" color="secondary.main"
            value={stats.rings.found}
            sub={`${stats.rings.accounts_involved.toLocaleString('en-IN')} accounts`}
            onClick={() => navigate('/rings')} />
        </Grid>
        <Grid item xs={6} md={2}>
          <StatCard icon={<ModelTrainingIcon />} label="Best model"
            value={stats.ml.trained ? `F1 ${(stats.ml.best_f1 * 100).toFixed(0)}%` : '—'}
            sub={stats.ml.best_model || 'not trained yet'} onClick={() => navigate('/ml')} />
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 2, height: 340 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Daily transactions (last 30 days of data)</Typography>
            <ResponsiveContainer width="100%" height={270}>
              <AreaChart data={stats.daily_transactions}>
                <defs>
                  <linearGradient id="txns" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4338ca" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#4338ca" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Area type="monotone" dataKey="transactions" stroke="#4338ca" fill="url(#txns)" name="All" />
                <Area type="monotone" dataKey="suspicious" stroke="#dc2626" fill="#dc2626"
                  fillOpacity={0.25} name="Suspicious" />
              </AreaChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2, height: 340 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Accounts by risk level</Typography>
            <ResponsiveContainer width="100%" height={270}>
              <PieChart>
                <Pie data={riskData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={95}
                  paddingAngle={2} label={(e) => `${e.name}: ${e.value.toLocaleString('en-IN')}`}>
                  {riskData.map((d) => <Cell key={d.name} fill={RISK_COLORS[d.name]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2, height: 340 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Alerts by status</Typography>
            {alertData.length ? (
              <ResponsiveContainer width="100%" height={270}>
                <BarChart data={alertData} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                  <Tooltip />
                  <Bar dataKey="value" name="Alerts" radius={[0, 4, 4, 0]}>
                    {alertData.map((d) => <Cell key={d.name} fill={STATUS_COLORS[d.name] || '#64748b'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No alerts yet — run the detection pipeline, then generate alerts.
              </Typography>
            )}
          </Paper>
        </Grid>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 2, height: 340, overflow: 'auto' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="h6">Highest-risk accounts</Typography>
              <Button size="small" onClick={() => navigate('/accounts')}>View all</Button>
            </Stack>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Account</TableCell>
                  <TableCell>Customer</TableCell>
                  <TableCell align="right">Fraud score</TableCell>
                  <TableCell>Risk</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stats.top_risk_accounts.map((a) => (
                  <TableRow key={a.account_uid} hover>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{a.account_uid}</TableCell>
                    <TableCell>{a.customer_name}</TableCell>
                    <TableCell align="right">
                      <Chip size="small" color="error" label={`${(a.fraud_score * 100).toFixed(0)}%`} />
                    </TableCell>
                    <TableCell><RiskChip level={a.risk_level} /></TableCell>
                  </TableRow>
                ))}
                {stats.top_risk_accounts.length === 0 && (
                  <TableRow><TableCell colSpan={4} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                    No high-risk accounts yet — run Rule Detection and ML Scoring.
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Suspicious volume: {money(stats.transactions.suspicious_volume)} of {money(stats.transactions.total_volume)} total.
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
