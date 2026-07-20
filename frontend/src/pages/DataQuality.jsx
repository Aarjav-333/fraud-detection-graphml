import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Card, CardContent, Button, Stack, Chip,
  CircularProgress, Snackbar, Alert,
} from '@mui/material'
import ReplayIcon from '@mui/icons-material/Replay'
import CleaningServicesIcon from '@mui/icons-material/CleaningServices'
import ConfirmDialog from '../components/ConfirmDialog'
import { getReport, runClean } from '../api/preprocessing'

const LABELS = {
  missing_fields: 'Missing fields',
  duplicates: 'Duplicate transactions',
  invalid_accounts: 'Invalid account refs',
  invalid_amounts: 'Invalid amounts',
  invalid_dates: 'Invalid / missing dates',
}

export default function DataQuality() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [toast, setToast] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try { setReport(await getReport()) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  async function doClean() {
    setConfirm(false)
    setLoading(true)
    try {
      const res = await runClean()
      setToast(`Removed ${res.removed} problematic transaction(s). ${res.remaining.toLocaleString('en-IN')} remain.`)
      await load()
    } finally { setLoading(false) }
  }

  const flagged = report?.total_flagged ?? 0

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Data Quality</Typography>
          <Typography variant="body2" color="text.secondary">
            Preprocessing checks before fraud analysis
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<ReplayIcon />} onClick={load} disabled={loading}>
            Re-run analysis
          </Button>
          <Button variant="contained" color="error" startIcon={<CleaningServicesIcon />}
            disabled={loading || flagged === 0} onClick={() => setConfirm(true)}>
            Clean data{flagged > 0 ? ` (${flagged})` : ''}
          </Button>
        </Stack>
      </Stack>

      {loading && !report ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : report && (
        <>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Grid container spacing={3}>
              <Grid item xs={6} sm={4}>
                <Typography variant="h4">{report.total_transactions.toLocaleString('en-IN')}</Typography>
                <Typography variant="body2" color="text.secondary">Total transactions</Typography>
              </Grid>
              <Grid item xs={6} sm={4}>
                <Typography variant="h4" color={flagged > 0 ? 'error.main' : 'success.main'}>{flagged}</Typography>
                <Typography variant="body2" color="text.secondary">Flagged for removal</Typography>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Chip
                  label={flagged === 0 ? 'Data is clean' : 'Issues found'}
                  color={flagged === 0 ? 'success' : 'warning'}
                  variant={flagged === 0 ? 'filled' : 'outlined'}
                />
              </Grid>
            </Grid>
          </Paper>

          <Grid container spacing={2}>
            {Object.entries(report.issues).map(([key, val]) => (
              <Grid item xs={12} sm={6} md={4} key={key}>
                <Card variant="outlined"
                  sx={{ borderColor: val.count > 0 ? 'warning.main' : 'divider', height: '100%' }}>
                  <CardContent>
                    <Typography variant="overline" color="text.secondary">{LABELS[key]}</Typography>
                    <Typography variant="h4" color={val.count > 0 ? 'warning.main' : 'text.primary'}>
                      {val.count}
                    </Typography>
                    {val.sample.length > 0 && (
                      <Typography variant="caption" color="text.secondary"
                        sx={{ display: 'block', mt: 1, fontFamily: 'monospace' }}>
                        {val.sample.join(', ')}{val.count > val.sample.length ? ' …' : ''}
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Alert severity="info" sx={{ mt: 3 }}>
            Cleaning removes duplicate transactions and drops rows with invalid accounts, amounts, or dates.
            Try it by uploading <b>data/raw/sample_messy.csv</b> on the Transactions page, then re-running the analysis.
          </Alert>
        </>
      )}

      <ConfirmDialog
        open={confirm} title="Clean data?"
        message={`${flagged} problematic transaction(s) will be permanently removed (duplicates and invalid rows).`}
        confirmText="Clean now" confirmColor="error"
        onConfirm={doClean} onClose={() => setConfirm(false)}
      />
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast('')} message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  )
}
