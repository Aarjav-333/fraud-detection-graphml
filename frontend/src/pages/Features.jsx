import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, FormControlLabel, Switch,
} from '@mui/material'
import BuildIcon from '@mui/icons-material/Build'
import TableChartIcon from '@mui/icons-material/TableChart'
import { buildFeatures, getFeaturesStatus, previewFeatures } from '../api/features'

const NUMERIC_COLS = [
  'total_sent', 'total_received', 'txn_count_sent', 'txn_count_received',
  'unique_receivers', 'unique_senders', 'avg_sent_amount', 'avg_received_amount',
  'max_sent_amount', 'max_received_amount', 'txn_per_active_day',
  'in_degree', 'out_degree', 'degree_centrality', 'pagerank', 'in_cycle', 'community_size',
]

export default function Features() {
  const [status, setStatus] = useState(null)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [rows, setRows] = useState([])
  const [fraudOnly, setFraudOnly] = useState(false)
  const [loadingRows, setLoadingRows] = useState(false)

  useEffect(() => { getFeaturesStatus().then(setStatus).catch(() => {}) }, [])

  const loadPreview = useCallback(async () => {
    if (!status?.has_run) return
    setLoadingRows(true)
    try { setRows(await previewFeatures({ limit: 12, fraudOnly })) }
    finally { setLoadingRows(false) }
  }, [status, fraudOnly])

  useEffect(() => { loadPreview() }, [loadPreview])

  async function handleBuild() {
    setBuilding(true); setError('')
    try {
      await buildFeatures()
      const s = await getFeaturesStatus()
      setStatus(s)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Feature build failed — is the backend running?')
    } finally { setBuilding(false) }
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Feature Engineering</Typography>
          <Typography variant="body2" color="text.secondary">
            Transaction + graph features per account — input to the ML models (workflow Step 9)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<BuildIcon />} onClick={handleBuild} disabled={building}>
          {building ? 'Building…' : 'Build feature matrix'}
        </Button>
      </Stack>

      {building && <Paper sx={{ p: 3, mb: 3 }}><LinearProgress /></Paper>}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {status?.has_run ? (
        <>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Grid container spacing={3}>
              <Grid item xs={6} sm={3}>
                <Typography variant="h4">{status.accounts?.toLocaleString('en-IN')}</Typography>
                <Typography variant="body2" color="text.secondary">Accounts (rows)</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="h4">{status.feature_list?.length}</Typography>
                <Typography variant="body2" color="text.secondary">Features (columns)</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="h4" color="error.main">{status.fraud_accounts?.toLocaleString('en-IN')}</Typography>
                <Typography variant="body2" color="text.secondary">Fraud accounts (labels)</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="h4">{(status.fraud_ratio * 100).toFixed(1)}%</Typography>
                <Typography variant="body2" color="text.secondary">Class imbalance ratio</Typography>
              </Grid>
            </Grid>
          </Paper>

          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} md={5}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Feature dictionary</Typography>
                <Table size="small">
                  <TableBody>
                    {status.feature_list?.map((f) => (
                      <TableRow key={f.name}>
                        <TableCell sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap', fontSize: 12 }}>{f.name}</TableCell>
                        <TableCell sx={{ fontSize: 12 }}>{f.description}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            </Grid>
            <Grid item xs={12} md={7}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="h6">Sample rows</Typography>
                  <FormControlLabel
                    control={<Switch checked={fraudOnly} onChange={(e) => setFraudOnly(e.target.checked)} />}
                    label="Fraud accounts only"
                  />
                </Stack>
                {loadingRows ? <LinearProgress /> : (
                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small" sx={{ '& td, & th': { fontSize: 11, whiteSpace: 'nowrap' } }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>account</TableCell>
                          {NUMERIC_COLS.slice(0, 8).map((c) => <TableCell key={c} align="right">{c}</TableCell>)}
                          <TableCell align="center">label</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {rows.map((r) => (
                          <TableRow key={r.account_uid} hover>
                            <TableCell sx={{ fontFamily: 'monospace' }}>{r.account_uid}</TableCell>
                            {NUMERIC_COLS.slice(0, 8).map((c) => (
                              <TableCell key={c} align="right">{Number(r[c]).toLocaleString('en-IN')}</TableCell>
                            ))}
                            <TableCell align="center">
                              {r.is_fraud
                                ? <Chip size="small" label="Fraud" color="error" />
                                : <Chip size="small" label="Legit" variant="outlined" />}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                      Showing the first 8 of {NUMERIC_COLS.length} feature columns. The full matrix is saved to
                      <b> backend/data/processed/features.csv</b>.
                    </Typography>
                  </Box>
                )}
              </Paper>
            </Grid>
          </Grid>

          <Alert severity="info" icon={<TableChartIcon />}>
            This matrix (transaction + graph features per account, with ground-truth labels) is exactly what
            the ML models in the next phase will train on. Rebuild it after re-running Graph Analysis so the
            graph columns stay in sync.
          </Alert>
        </>
      ) : !building && (
        <Alert severity="info">
          Run <b>Graph Analysis</b> first (so graph metrics exist), then click <b>Build feature matrix</b>.
        </Alert>
      )}
    </Box>
  )
}
