import { useEffect, useState, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell,
} from '@mui/material'
import ModelTrainingIcon from '@mui/icons-material/ModelTraining'
import { getMLStatus, trainModels, getTopRisk } from '../api/ml'

const MODEL_LABELS = {
  random_forest: 'Random Forest (class-weighted)',
  xgboost: 'XGBoost (scale_pos_weight)',
  isolation_forest: 'Isolation Forest (unsupervised)',
}
const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')

export default function MLScoring() {
  const [results, setResults] = useState(null)
  const [topRisk, setTopRisk] = useState([])
  const [training, setTraining] = useState(false)
  const [error, setError] = useState('')

  const loadAll = useCallback(async () => {
    try {
      const s = await getMLStatus()
      if (s.has_run) {
        setResults(s.results)
        setTopRisk(await getTopRisk(15))
      }
    } catch { /* backend not ready */ }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  async function handleTrain() {
    setTraining(true); setError('')
    try {
      const res = await trainModels()
      setResults(res)
      setTopRisk(await getTopRisk(15))
    } catch (err) {
      setError(err?.response?.data?.detail || 'Training failed — build the feature matrix first.')
    } finally { setTraining(false) }
  }

  const maxImportance = results?.top_features?.[0]?.importance || 1

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">ML Risk Scoring</Typography>
          <Typography variant="body2" color="text.secondary">
            Baseline models + anomaly detection with class-imbalance handling (workflow Step 10)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<ModelTrainingIcon />} onClick={handleTrain} disabled={training}>
          {training ? 'Training…' : 'Train & score'}
        </Button>
      </Stack>

      {training && <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="body2" sx={{ mb: 1 }}>Training Random Forest, XGBoost and Isolation Forest on the feature matrix…</Typography>
        <LinearProgress />
      </Paper>}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {results ? (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="h6">Model comparison (held-out test set)</Typography>
              <Chip color="primary" label={`Best: ${MODEL_LABELS[results.best_model] || results.best_model}`} />
            </Stack>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Model</TableCell>
                  <TableCell align="right">Accuracy</TableCell>
                  <TableCell align="right">Precision</TableCell>
                  <TableCell align="right">Recall</TableCell>
                  <TableCell align="right">F1</TableCell>
                  <TableCell align="right">ROC-AUC</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(results.results || {}).map(([name, m]) => (
                  <TableRow key={name} hover selected={name === results.best_model}>
                    <TableCell>{MODEL_LABELS[name] || name}</TableCell>
                    <TableCell align="right">{pct(m.accuracy)}</TableCell>
                    <TableCell align="right">{pct(m.precision)}</TableCell>
                    <TableCell align="right">{pct(m.recall)}</TableCell>
                    <TableCell align="right"><b>{pct(m.f1)}</b></TableCell>
                    <TableCell align="right">{pct(m.roc_auc)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Train {results.train_size?.toLocaleString('en-IN')} / test {results.test_size?.toLocaleString('en-IN')} accounts,
              stratified. Class imbalance handled with class weights (RF) and scale_pos_weight (XGBoost).
            </Typography>
          </Paper>

          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} md={5}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" sx={{ mb: 1.5 }}>Top feature importances</Typography>
                {results.top_features?.map((f) => (
                  <Box key={f.feature} sx={{ mb: 1.2 }}>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>{f.feature}</Typography>
                      <Typography variant="caption" color="text.secondary">{(f.importance * 100).toFixed(1)}%</Typography>
                    </Stack>
                    <LinearProgress variant="determinate" value={(f.importance / maxImportance) * 100}
                      sx={{ height: 8, borderRadius: 4 }} />
                  </Box>
                ))}
                <Typography variant="caption" color="text.secondary">
                  Graph features (pagerank, degrees, cycles) appearing here shows the network structure
                  genuinely improves detection.
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} md={7}>
              <Paper sx={{ p: 2, height: '100%' }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Highest-risk accounts (model score)</Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Account</TableCell>
                      <TableCell>Name</TableCell>
                      <TableCell align="right">Fraud score</TableCell>
                      <TableCell align="center">Ground truth</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {topRisk.map((r) => (
                      <TableRow key={r.account_uid} hover>
                        <TableCell sx={{ fontFamily: 'monospace' }}>{r.account_uid}</TableCell>
                        <TableCell>{r.customer_name}</TableCell>
                        <TableCell align="right">
                          <Chip size="small" color={r.fraud_score >= 0.8 ? 'error' : 'warning'}
                            label={(r.fraud_score * 100).toFixed(1) + '%'} />
                        </TableCell>
                        <TableCell align="center">
                          {r.is_fraud
                            ? <Chip size="small" label="Fraud" color="error" variant="outlined" />
                            : <Chip size="small" label="Legit" variant="outlined" />}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            </Grid>
          </Grid>

          <Alert severity="info">
            Every account now has a <b>fraud_score</b> (0–100%). These scores drive the fraud alerts in the
            next phase. Scores are from the best model ({MODEL_LABELS[results.best_model]}).
          </Alert>
        </>
      ) : !training && (
        <Alert severity="info">
          Prerequisites: run <b>Graph Analysis</b>, then <b>Features → Build feature matrix</b>.
          Then click <b>Train & score</b> (takes a few seconds).
        </Alert>
      )}
    </Box>
  )
}
