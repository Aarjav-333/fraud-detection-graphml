import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Alert, CircularProgress, Divider,
} from '@mui/material'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import TableViewIcon from '@mui/icons-material/TableView'
import DownloadIcon from '@mui/icons-material/Download'
import { listExports, downloadCsv, downloadSummaryPdf } from '../api/reports'

const CSV_LABELS = {
  suspicious_transactions: 'Suspicious transactions',
  high_risk_accounts: 'High-risk accounts',
  alerts: 'Fraud alerts',
  cases: 'Investigation cases',
}

export default function Reports() {
  const [exports, setExports] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { listExports().then(setExports).catch(() => {}) }, [])

  async function handle(fn, key) {
    setBusy(key); setError('')
    try { await fn() }
    catch { setError('Download failed — is the backend running and the pipeline executed?') }
    finally { setBusy('') }
  }

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 0.5 }}>Reports & Export</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Downloadable deliverables (workflow Step 15)
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      <Grid container spacing={2}>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 3, height: '100%' }}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
              <PictureAsPdfIcon color="error" fontSize="large" />
              <Typography variant="h6">System summary report (PDF)</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              A one-page professional summary: data overview, model performance
              (baselines + GNN), fraud rings, and alert/case outcomes. Ideal for
              attaching to your project report or showing in a viva.
            </Typography>
            <Button variant="contained" startIcon={busy === 'pdf' ? <CircularProgress size={16} color="inherit" /> : <DownloadIcon />}
              disabled={!!busy} onClick={() => handle(downloadSummaryPdf, 'pdf')}>
              Download PDF
            </Button>
          </Paper>
        </Grid>

        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 3, height: '100%' }}>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
              <TableViewIcon color="primary" fontSize="large" />
              <Typography variant="h6">CSV data exports</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Raw tables for further analysis in Excel, pandas, or your report appendix.
            </Typography>
            <Stack divider={<Divider />} spacing={1.5}>
              {exports.map((e) => (
                <Stack key={e.name} direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography variant="body1">{CSV_LABELS[e.name] || e.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{e.description}</Typography>
                  </Box>
                  <Button size="small" variant="outlined"
                    startIcon={busy === e.name ? <CircularProgress size={14} /> : <DownloadIcon />}
                    disabled={!!busy} onClick={() => handle(() => downloadCsv(e.name), e.name)}>
                    CSV
                  </Button>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <Alert severity="info" sx={{ mt: 3 }}>
        Reports reflect the current database state — run the full pipeline
        (Rules → ML → Alerts → Rings) first for a complete report.
      </Alert>
    </Box>
  )
}
