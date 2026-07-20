import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, ToggleButtonGroup, ToggleButton,
  TextField,
} from '@mui/material'
import PsychologyIcon from '@mui/icons-material/Psychology'
import { getGNNStatus, trainGNN } from '../api/gnn'
import { getMLStatus } from '../api/ml'

const SOURCE_LABELS = {
  synthetic: 'Synthetic account graph (this system)',
  elliptic: 'Elliptic Bitcoin dataset (research benchmark)',
}
const MODEL_LABELS = { gcn: 'GCN', graphsage: 'GraphSAGE' }
const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')

export default function GNN() {
  const [status, setStatus] = useState(null)
  const [baseline, setBaseline] = useState(null)
  const [source, setSource] = useState('synthetic')
  const [model, setModel] = useState('graphsage')
  const [epochs, setEpochs] = useState(100)
  const [training, setTraining] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getGNNStatus().then(setStatus).catch(() => {})
    getMLStatus().then((s) => s.has_run && setBaseline(s.results)).catch(() => {})
  }, [])

  async function handleTrain() {
    setTraining(true); setError('')
    try {
      await trainGNN({ source, model, epochs })
      setStatus(await getGNNStatus())
    } catch (err) {
      setError(err?.response?.data?.detail ||
        'Training failed. If this is the Elliptic dataset, the first run downloads ~500MB — check the backend terminal.')
    } finally { setTraining(false) }
  }

  const results = status?.results || {}
  const resultKeys = Object.keys(results)
  const bestBaselineF1 = baseline
    ? Math.max(baseline.results?.random_forest?.f1 ?? 0, baseline.results?.xgboost?.f1 ?? 0)
    : null

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Graph Neural Network</Typography>
          <Typography variant="body2" color="text.secondary">
            GCN / GraphSAGE node classification (workflow Step 10 — Graph ML)
          </Typography>
        </Box>
      </Stack>

      {status && !status.deps_installed && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          GNN dependencies are not installed. From the <b>backend</b> folder (venv active) run:
          <Box component="code" sx={{ display: 'block', mt: 1, fontFamily: 'monospace' }}>
            pip install -r requirements-gnn.txt
          </Box>
          This installs PyTorch (~200MB+) and PyTorch Geometric, then restart the backend.
        </Alert>
      )}

      <Paper sx={{ p: 2.5, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Train a model</Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={5}>
            <Typography variant="caption" color="text.secondary">Data source</Typography>
            <ToggleButtonGroup exclusive fullWidth size="small" value={source}
              onChange={(e, v) => v && setSource(v)} sx={{ mt: 0.5 }}>
              <ToggleButton value="synthetic">Synthetic graph</ToggleButton>
              <ToggleButton value="elliptic">Elliptic Bitcoin</ToggleButton>
            </ToggleButtonGroup>
          </Grid>
          <Grid item xs={12} md={3}>
            <Typography variant="caption" color="text.secondary">Model</Typography>
            <ToggleButtonGroup exclusive fullWidth size="small" value={model}
              onChange={(e, v) => v && setModel(v)} sx={{ mt: 0.5 }}>
              <ToggleButton value="graphsage">GraphSAGE</ToggleButton>
              <ToggleButton value="gcn">GCN</ToggleButton>
            </ToggleButtonGroup>
          </Grid>
          <Grid item xs={6} md={2}>
            <TextField label="Epochs" type="number" size="small" fullWidth value={epochs}
              onChange={(e) => setEpochs(Math.max(10, Math.min(500, Number(e.target.value) || 100)))} />
          </Grid>
          <Grid item xs={6} md={2}>
            <Button fullWidth variant="contained" startIcon={<PsychologyIcon />}
              onClick={handleTrain} disabled={training || (status && !status.deps_installed)}>
              {training ? 'Training…' : 'Train'}
            </Button>
          </Grid>
        </Grid>
        {source === 'elliptic' && (
          <Alert severity="info" sx={{ mt: 2 }}>
            First Elliptic run downloads ~500MB and trains on ~200k nodes — expect several minutes on CPU.
            Progress appears in the backend terminal.
          </Alert>
        )}
      </Paper>

      {training && <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="body2" sx={{ mb: 1 }}>
          Training {MODEL_LABELS[model]} on {SOURCE_LABELS[source]}…
        </Typography>
        <LinearProgress />
      </Paper>}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {resultKeys.length > 0 && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>Results</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Source</TableCell>
                <TableCell>Model</TableCell>
                <TableCell align="right">Nodes (train/test)</TableCell>
                <TableCell align="right">Accuracy</TableCell>
                <TableCell align="right">Precision</TableCell>
                <TableCell align="right">Recall</TableCell>
                <TableCell align="right">F1</TableCell>
                <TableCell align="right">ROC-AUC</TableCell>
                <TableCell align="right">Time</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {resultKeys.map((k) => {
                const r = results[k]
                return (
                  <TableRow key={k} hover>
                    <TableCell>{SOURCE_LABELS[r.source] || r.source}</TableCell>
                    <TableCell><Chip size="small" label={MODEL_LABELS[r.model] || r.model} /></TableCell>
                    <TableCell align="right">{r.train_nodes?.toLocaleString('en-IN')} / {r.test_nodes?.toLocaleString('en-IN')}</TableCell>
                    <TableCell align="right">{pct(r.metrics?.accuracy)}</TableCell>
                    <TableCell align="right">{pct(r.metrics?.precision)}</TableCell>
                    <TableCell align="right">{pct(r.metrics?.recall)}</TableCell>
                    <TableCell align="right"><b>{pct(r.metrics?.f1)}</b></TableCell>
                    <TableCell align="right">{pct(r.metrics?.roc_auc)}</TableCell>
                    <TableCell align="right">{r.train_seconds}s</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          {bestBaselineF1 != null && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              For comparison, the best baseline (Phase 9A) reached F1 {pct(bestBaselineF1)} on the synthetic accounts.
              Note: baselines classify accounts; the Elliptic GNN classifies Bitcoin transactions — compare within the
              same source, not across.
            </Typography>
          )}
        </Paper>
      )}

      {resultKeys.length === 0 && !training && status?.deps_installed && (
        <Alert severity="info">
          Prerequisites for the synthetic graph: Graph Analysis + Features built. Then pick a source and model
          and click <b>Train</b>. Elliptic needs no prerequisites — it downloads automatically.
        </Alert>
      )}
    </Box>
  )
}
