import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, CircularProgress, Alert,
  Table, TableHead, TableBody, TableRow, TableCell, LinearProgress,
} from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import GavelIcon from '@mui/icons-material/Gavel'
import { useNavigate } from 'react-router-dom'
import { getRulesStatus, runRules } from '../api/rules'

export default function RuleDetection() {
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { getRulesStatus().then(setStatus).catch(() => {}) }, [])

  async function handleRun() {
    setRunning(true); setError(''); setResult(null)
    try {
      const res = await runRules()
      setResult(res)
      setStatus({ total_transactions: res.total_transactions, total_suspicious: res.total_suspicious, has_run: true })
    } catch (err) {
      setError(err?.response?.data?.detail || 'Rule engine failed — is the backend running?')
    } finally {
      setRunning(false)
    }
  }

  const evalData = result?.evaluation

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Rule-Based Detection</Typography>
          <Typography variant="body2" color="text.secondary">
            Business-logic fraud rules — no ML involved (workflow Step 6)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={running ? null : <PlayArrowIcon />}
          onClick={handleRun} disabled={running}>
          {running ? 'Running rules…' : 'Run all rules'}
        </Button>
      </Stack>

      {running && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Scanning all transactions against 6 rules — this takes about a minute on 80k transactions.
          </Typography>
          <LinearProgress />
        </Paper>
      )}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {status && !running && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={6} sm={3}>
              <Typography variant="h4">{(status.total_transactions ?? 0).toLocaleString('en-IN')}</Typography>
              <Typography variant="body2" color="text.secondary">Transactions scanned</Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="h4" color={status.total_suspicious > 0 ? 'warning.main' : 'text.primary'}>
                {(status.total_suspicious ?? 0).toLocaleString('en-IN')}
              </Typography>
              <Typography variant="body2" color="text.secondary">Marked suspicious</Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              {status.has_run
                ? <Chip color="success" icon={<GavelIcon />} label="Rules have been applied" />
                : <Chip variant="outlined" label="Rules not run yet — click 'Run all rules'" />}
            </Grid>
          </Grid>
        </Paper>
      )}

      {result && (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Hits per rule</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Rule</TableCell>
                  <TableCell align="right">Transactions flagged</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {result.rules.map((r) => (
                  <TableRow key={r.rule} hover>
                    <TableCell>{r.label}</TableCell>
                    <TableCell align="right">
                      <Chip size="small" label={r.count}
                        color={r.count > 0 ? 'warning' : 'default'}
                        variant={r.count > 0 ? 'filled' : 'outlined'} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Account risk levels raised</Typography>
                <Stack direction="row" spacing={2}>
                  <Chip color="warning" label={`${result.accounts_risk.medium} Medium`} />
                  <Chip color="error" label={`${result.accounts_risk.high} High`} />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
                  Accounts hit by one rule → Medium. Hit by two or more rules → High.
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Evaluation vs ground truth</Typography>
                {evalData && (
                  <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                    <Chip label={`Precision ${(evalData.precision * 100).toFixed(1)}%`} color="success" variant="outlined" />
                    <Chip label={`Recall ${(evalData.recall * 100).toFixed(1)}%`} color="success" variant="outlined" />
                    <Chip label={`TP ${evalData.true_positives}`} variant="outlined" />
                    <Chip label={`FP ${evalData.false_positives}`} variant="outlined" />
                    <Chip label={`FN ${evalData.false_negatives}`} variant="outlined" />
                  </Stack>
                )}
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
                  Measured against the planted fraud labels in the synthetic dataset.
                </Typography>
              </Paper>
            </Grid>
          </Grid>

          <Alert severity="info" action={
            <Button size="small" onClick={() => navigate('/transactions')}>View transactions</Button>
          }>
            Flagged transactions now show status <b>suspicious</b> on the Transactions page, and involved
            accounts show raised risk levels on the Accounts page.
          </Alert>
        </>
      )}
    </Box>
  )
}
