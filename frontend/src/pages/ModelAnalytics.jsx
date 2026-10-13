import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Box, Button, Chip, Grid, LinearProgress, Paper, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, ToggleButton, ToggleButtonGroup, Tooltip as MuiTooltip, Typography,
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getGNNEvaluation } from '../api/gnn'
import { eventTime } from '../utils/format'

// Categorical slots validated for this pair (CVD ΔE 24.7, contrast >= 3:1 on white);
// red/amber/green stay reserved for risk levels elsewhere in the app.
const MODELS = [
  { key: 'graphsage', label: 'GraphSAGE', color: '#2a78d6' },
  { key: 'gcn', label: 'GCN', color: '#eb6834' },
]
const SOURCES = [
  { key: 'synthetic', label: 'Synthetic account graph' },
  { key: 'elliptic', label: 'Elliptic Bitcoin' },
]
const BAR_METRICS = [
  ['accuracy', 'Accuracy'], ['precision', 'Precision'], ['recall', 'Recall'],
  ['f1', 'F1-score'], ['roc_auc', 'ROC-AUC'], ['pr_auc', 'PR-AUC'],
]
const TABLE_METRICS = [...BAR_METRICS, ['false_positive_rate', 'False positive rate'], ['false_negative_rate', 'False negative rate']]
const GRID = '#eef0f3'
const AXIS = { fontSize: 12, fill: '#6b7280' }
const REFERENCE = '#9ca3af'
const BLUES = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281']

const pct = (v, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`)
const num = (v, d = 3) => (v == null ? '—' : Number(v).toFixed(d))
const count = (v) => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

function Section({ title, subtitle, children, sx }) {
  return (
    <Paper sx={{ p: 2.5, height: '100%', ...sx }}>
      <Typography variant="h6">{title}</Typography>
      {subtitle && <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{subtitle}</Typography>}
      {children}
    </Paper>
  )
}

function Swatch({ color, dashed }) {
  return (
    <Box component="span" sx={{ display: 'inline-block', width: 14, height: 0, mr: 0.75, verticalAlign: 'middle',
                                borderTop: `2px ${dashed ? 'dashed' : 'solid'} ${color}` }} />
  )
}

function NotRecorded({ children }) {
  return (
    <Box sx={{ py: 5, textAlign: 'center' }}>
      <Typography variant="body2" color="text.secondary">{children}</Typography>
    </Box>
  )
}

function CurveTooltip({ active, payload, xLabel, yLabel }) {
  if (!active || !payload?.length) return null
  return (
    <Paper sx={{ p: 1.25, fontSize: 12 }} elevation={3}>
      {payload.map((p) => (
        <Box key={p.name} sx={{ mb: 0.25 }}>
          <Swatch color={p.color} dashed={p.strokeDasharray} />
          <b>{p.name}</b>: {xLabel} {num(p.payload.x)} · {yLabel} {num(p.payload.y)}
        </Box>
      ))}
    </Paper>
  )
}

function ConfusionMatrix({ model, evaluation }) {
  const cm = evaluation.confusion_matrix
  const total = cm.tn + cm.fp + cm.fn + cm.tp
  const actualLegit = cm.tn + cm.fp
  const actualFraud = cm.fn + cm.tp
  const cell = (key, short, label, value, rowTotal, meaning) => {
    const share = total ? value / total : 0
    const step = Math.min(BLUES.length - 1, Math.round(Math.sqrt(share) * (BLUES.length - 1)))
    const dark = step >= 6
    return (
      <MuiTooltip key={key} arrow title={`${label}: ${count(value)} of ${count(rowTotal)} (${pct(rowTotal ? value / rowTotal : 0)}). ${meaning}`}>
        <Box sx={{ bgcolor: BLUES[step], color: dark ? '#fff' : '#111827', borderRadius: 1, p: 1.5, minHeight: 92,
                   display: 'flex', flexDirection: 'column', justifyContent: 'center', textAlign: 'center' }}>
          <Typography variant="caption" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>{short} · {label}</Typography>
          <Typography variant="h5" sx={{ lineHeight: 1.3 }}>{count(value)}</Typography>
          <Typography variant="caption">{pct(rowTotal ? value / rowTotal : 0)} of actual {key === 'tn' || key === 'fp' ? 'legit' : 'fraud'}</Typography>
        </Box>
      </MuiTooltip>
    )
  }
  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: model.color }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{model.label}</Typography>
      </Stack>
      <Box sx={{ display: 'grid', gridTemplateColumns: '84px 1fr 1fr', gap: '2px', alignItems: 'stretch' }}>
        <Box />
        <Typography variant="caption" color="text.secondary" align="center">Predicted legit</Typography>
        <Typography variant="caption" color="text.secondary" align="center">Predicted fraud</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>Actual legit</Typography>
        {cell('tn', 'TN', 'True negatives', cm.tn, actualLegit, 'Legitimate, correctly left alone.')}
        {cell('fp', 'FP', 'False positives', cm.fp, actualLegit, 'Legitimate, wrongly flagged as fraud.')}
        <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>Actual fraud</Typography>
        {cell('fn', 'FN', 'False negatives', cm.fn, actualFraud, 'Fraud the model missed.')}
        {cell('tp', 'TP', 'True positives', cm.tp, actualFraud, 'Fraud correctly caught.')}
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 1.5 }}>
        <Typography variant="body2">False positive rate <b>{pct(evaluation.metrics.false_positive_rate)}</b></Typography>
        <Typography variant="body2">False negative rate <b>{pct(evaluation.metrics.false_negative_rate)}</b></Typography>
      </Stack>
    </Box>
  )
}

export default function ModelAnalytics() {
  const navigate = useNavigate()
  const [source, setSource] = useState('synthetic')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setReport(await getGNNEvaluation(source))
      setError('')
    } catch (err) {
      setError(err?.response?.status === 403
        ? 'Model analytics are for fraud analyst accounts.'
        : 'Could not load the evaluation results. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [source])

  useEffect(() => { load() }, [load])

  const present = report ? MODELS.filter((m) => report.models[m.key]) : []
  const detailed = present.filter((m) => report.models[m.key].detailed)
  const first = present.length ? report.models[present[0].key] : null
  const support = detailed.length ? report.models[detailed[0].key].evaluation.support : null
  const positiveRate = support ? support.positives / (support.positives + support.negatives) : null

  const barData = BAR_METRICS.map(([key, label]) => {
    const row = { metric: label }
    present.forEach((m) => { row[m.key] = report.models[m.key].metrics?.[key] ?? null })
    return row
  })
  const curve = (m, kind) => {
    const c = report.models[m.key].evaluation?.[kind]
    if (!c || !Object.keys(c).length) return []
    return kind === 'roc_curve' ? c.fpr.map((x, i) => ({ x, y: c.tpr[i] })) : c.recall.map((x, i) => ({ x, y: c.precision[i] }))
  }
  const withHistory = present.filter((m) => report.models[m.key].history?.length)
  const historyLine = (m, field) => report.models[m.key].history.map((h) => ({ x: h.epoch, y: h[field] }))

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Model Analytics</Typography>
          <Typography variant="body2" color="text.secondary">
            GraphSAGE vs GCN, evaluated on the same held-out test nodes (workflow Step 10 — Graph ML)
          </Typography>
        </Box>
      </Stack>

      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <ToggleButtonGroup exclusive size="small" value={source} onChange={(e, v) => v && setSource(v)}>
          {SOURCES.map((s) => (
            <ToggleButton key={s.key} value={s.key}>
              {s.label}
              {report && !report.sources_with_results.includes(s.key) && ' (no results)'}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <Button size="small" startIcon={<RefreshIcon />} onClick={load} disabled={loading}>Refresh</Button>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {error && (
        <Alert severity={error.includes('analyst') ? 'warning' : 'error'} sx={{ mb: 2 }}
          action={!error.includes('analyst') && <Button color="inherit" size="small" onClick={load}>Retry</Button>}>
          {error}
        </Alert>
      )}

      {report && present.length === 0 && !loading && (
        <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => navigate('/gnn')}>Go to GNN</Button>}>
          No GraphSAGE or GCN results for the {SOURCES.find((s) => s.key === source).label.toLowerCase()} yet.
          Train both models on the GNN page; their evaluation is saved and shown here without retraining.
        </Alert>
      )}

      {report && present.length > 0 && (
        <Box sx={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.2s' }}>
          <Paper sx={{ p: 2.5, mb: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="text.secondary">Evaluation dataset</Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{first.dataset?.name || SOURCES.find((s) => s.key === source).label}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {count(first.dataset?.nodes)} nodes · {count(first.dataset?.edges)} edges · {first.dataset?.features} features
                </Typography>
                <Typography variant="body2" color="text.secondary">Split: {first.dataset?.split}</Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="text.secondary">Held-out test set</Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{count(first.test_nodes)} nodes</Typography>
                {support && (
                  <Typography variant="body2" color="text.secondary">
                    {count(support.positives)} fraud · {count(support.negatives)} legitimate ({pct(positiveRate)} fraud)
                  </Typography>
                )}
                <Typography variant="body2" color="text.secondary">
                  Decision threshold: {first.threshold != null ? `fraud probability ≥ ${first.threshold}` : 'not recorded'}
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="text.secondary">Fair comparison</Typography>
                {report.same_test_split === true && (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CheckCircleOutlineIcon color="success" fontSize="small" />
                    <Typography variant="body2">Both models were tested on the identical test nodes.</Typography>
                  </Stack>
                )}
                {report.same_test_split === false && (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <ErrorOutlineIcon color="error" fontSize="small" />
                    <Typography variant="body2">The two models were tested on different nodes — retrain both to compare them.</Typography>
                  </Stack>
                )}
                {report.same_test_split == null && (
                  <Typography variant="body2" color="text.secondary">
                    {present.length < 2 ? 'Train the other model too for a side-by-side comparison.'
                      : 'Can\'t be verified for results saved before evaluations were recorded — retrain both models.'}
                  </Typography>
                )}
              </Grid>
            </Grid>
          </Paper>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            {MODELS.map((m) => {
              const r = report.models[m.key]
              return (
                <Grid item xs={12} md={6} key={m.key}>
                  <Paper sx={{ p: 2.5, height: '100%', borderTop: `3px solid ${m.color}` }}>
                    <Typography variant="h6">{m.label}</Typography>
                    {!r ? (
                      <Typography variant="body2" color="text.secondary">Not trained on this source yet.</Typography>
                    ) : (
                      <>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 1 }}>{r.model_version || 'version not recorded'}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          Trained {r.trained_at ? eventTime(r.trained_at) : '—'} · evaluated {r.evaluated_at ? eventTime(r.evaluated_at) : '—'}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {r.epochs} epochs · {count(r.train_nodes)} train / {r.val_nodes != null ? `${count(r.val_nodes)} validation / ` : ''}{count(r.test_nodes)} test nodes
                          {r.train_seconds != null && ` · ${r.train_seconds}s`}
                        </Typography>
                        {!r.detailed && (
                          <Alert severity="info" sx={{ mt: 1.5 }}>
                            Saved before full evaluations were recorded: only its summary metrics exist. Retrain it on the GNN
                            page to record the ROC and PR curves, confusion matrix and training curves.
                          </Alert>
                        )}
                      </>
                    )}
                  </Paper>
                </Grid>
              )
            })}
          </Grid>

          <Section title="Model comparison" subtitle="Test-set metrics at the decision threshold (ROC-AUC and PR-AUC are threshold-free)"
            sx={{ mb: 2 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barData} barGap={2} barCategoryGap="28%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis dataKey="metric" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} />
                <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={AXIS} axisLine={false} tickLine={false} width={44} />
                <Tooltip formatter={(v, name) => [pct(v, 2), name]} cursor={{ fill: 'rgba(17,24,39,0.04)' }} />
                <Legend iconType="circle" itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
                {present.map((m) => (
                  <Bar key={m.key} dataKey={m.key} name={m.label} fill={m.color} maxBarSize={24} radius={[4, 4, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
            <Box sx={{ overflowX: 'auto', mt: 1 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Metric</TableCell>
                    {present.map((m) => <TableCell key={m.key} align="right"><Swatch color={m.color} />{m.label}</TableCell>)}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {TABLE_METRICS.map(([key, label]) => (
                    <TableRow key={key}>
                      <TableCell>{label}</TableCell>
                      {present.map((m) => (
                        <TableCell key={m.key} align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                          {pct(report.models[m.key].metrics?.[key], 2)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell>TP / FP / TN / FN</TableCell>
                    {present.map((m) => {
                      const cm = report.models[m.key].evaluation?.confusion_matrix
                      return (
                        <TableCell key={m.key} align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                          {cm ? `${count(cm.tp)} / ${count(cm.fp)} / ${count(cm.tn)} / ${count(cm.fn)}` : '—'}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                </TableBody>
              </Table>
            </Box>
          </Section>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={6}>
              <Section title="ROC curve" subtitle="True positive rate against false positive rate as the threshold varies">
                {detailed.length === 0 ? <NotRecorded>No ROC curve was recorded for these results.</NotRecorded> : (
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                      <CartesianGrid stroke={GRID} />
                      <XAxis type="number" dataKey="x" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS}
                        label={{ value: 'False positive rate', position: 'insideBottom', offset: -10, fontSize: 12, fill: '#6b7280' }} />
                      <YAxis type="number" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS} width={60}
                        label={{ value: 'True positive rate', angle: -90, position: 'insideLeft', offset: 4, fontSize: 12, fill: '#6b7280' }} />
                      <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={REFERENCE} strokeDasharray="4 4"
                        label={{ value: 'Chance', position: 'insideTopLeft', fontSize: 11, fill: '#6b7280' }} />
                      <Tooltip content={<CurveTooltip xLabel="FPR" yLabel="TPR" />} />
                      <Legend verticalAlign="top" height={30} iconType="plainline" itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
                      {detailed.map((m) => (
                        <Line key={m.key} data={curve(m, 'roc_curve')} dataKey="y" type="linear" stroke={m.color} strokeWidth={2}
                          dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} isAnimationActive={false}
                          name={`${m.label} (AUC ${num(report.models[m.key].metrics.roc_auc)})`} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </Section>
            </Grid>
            <Grid item xs={12} md={6}>
              <Section title="Precision-recall curve"
                subtitle={positiveRate != null
                  ? `Only ${pct(positiveRate)} of the test nodes are fraud, so this is the curve to watch: the dashed line is what a random model would score`
                  : 'Precision against recall as the threshold varies'}>
                {detailed.length === 0 ? <NotRecorded>No precision-recall curve was recorded for these results.</NotRecorded> : (
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                      <CartesianGrid stroke={GRID} />
                      <XAxis type="number" dataKey="x" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS}
                        label={{ value: 'Recall', position: 'insideBottom', offset: -10, fontSize: 12, fill: '#6b7280' }} />
                      <YAxis type="number" domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS} width={60}
                        label={{ value: 'Precision', angle: -90, position: 'insideLeft', offset: 4, fontSize: 12, fill: '#6b7280' }} />
                      {positiveRate != null && (
                        <ReferenceLine y={positiveRate} stroke={REFERENCE} strokeDasharray="4 4"
                          label={{ value: `Random: ${pct(positiveRate)}`, position: 'insideBottomLeft', fontSize: 11, fill: '#6b7280' }} />
                      )}
                      <Tooltip content={<CurveTooltip xLabel="Recall" yLabel="Precision" />} />
                      <Legend verticalAlign="top" height={30} iconType="plainline" itemSorter={null} wrapperStyle={{ fontSize: 13 }} />
                      {detailed.map((m) => (
                        <Line key={m.key} data={curve(m, 'pr_curve')} dataKey="y" type="linear" stroke={m.color} strokeWidth={2}
                          dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} isAnimationActive={false}
                          name={`${m.label} (AP ${num(report.models[m.key].metrics.pr_auc)})`} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                )}
                {detailed.length === 2 && (() => {
                  const [a, b] = detailed.map((m) => ({ ...m, ap: report.models[m.key].metrics.pr_auc }))
                  const [hi, lo] = a.ap >= b.ap ? [a, b] : [b, a]
                  return (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      {hi.label} keeps higher precision across recall levels: average precision {num(hi.ap)} vs {num(lo.ap)}
                      {positiveRate != null && ` (a random model: ${num(positiveRate)})`}.
                    </Typography>
                  )
                })()}
              </Section>
            </Grid>
          </Grid>

          <Section title="Confusion matrices" subtitle="Test nodes by actual and predicted class at the decision threshold; darker = more nodes"
            sx={{ mb: 2 }}>
            {detailed.length === 0 ? <NotRecorded>No confusion matrix was recorded for these results.</NotRecorded> : (
              <Grid container spacing={3}>
                {detailed.map((m) => (
                  <Grid item xs={12} md={6} key={m.key}>
                    <ConfusionMatrix model={m} evaluation={report.models[m.key].evaluation} />
                  </Grid>
                ))}
              </Grid>
            )}
          </Section>

          <Grid container spacing={2}>
            {[['loss', 'Training and validation loss', 'Weighted cross-entropy per epoch (as used in training)', 'Loss'],
              ['accuracy', 'Training and validation accuracy', 'Share of nodes classified correctly per epoch', 'Accuracy']].map(([kind, title, subtitle, yName]) => (
              <Grid item xs={12} md={6} key={kind}>
                <Section title={title} subtitle={subtitle}>
                  {withHistory.length === 0 ? (
                    <NotRecorded>Training history wasn't recorded for these runs. Retrain on the GNN page to see it.</NotRecorded>
                  ) : (
                    <>
                      <ResponsiveContainer width="100%" height={280}>
                        <LineChart margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                          <CartesianGrid stroke={GRID} />
                          <XAxis type="number" dataKey="x" domain={['dataMin', 'dataMax']} tick={AXIS} allowDecimals={false}
                            label={{ value: 'Epoch', position: 'insideBottom', offset: -10, fontSize: 12, fill: '#6b7280' }} />
                          <YAxis type="number" tick={AXIS} width={48}
                            domain={kind === 'accuracy' ? [0, 1] : [0, 'auto']}
                            tickFormatter={kind === 'accuracy' ? (v) => `${Math.round(v * 100)}%` : (v) => v.toFixed(2)} />
                          <Tooltip content={<CurveTooltip xLabel="epoch" yLabel={yName.toLowerCase()} />} />
                          {withHistory.flatMap((m) => [
                            <Line key={`${m.key}-train`} data={historyLine(m, `train_${kind}`)} dataKey="y" stroke={m.color}
                              strokeWidth={2} dot={false} isAnimationActive={false} name={`${m.label} training`} />,
                            <Line key={`${m.key}-val`} data={historyLine(m, `val_${kind}`)} dataKey="y" stroke={m.color}
                              strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} name={`${m.label} validation`} />,
                          ])}
                        </LineChart>
                      </ResponsiveContainer>
                      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                        {withHistory.flatMap((m) => [
                          <Typography key={`${m.key}-t`} variant="caption"><Swatch color={m.color} />{m.label} training</Typography>,
                          <Typography key={`${m.key}-v`} variant="caption"><Swatch color={m.color} dashed />{m.label} validation</Typography>,
                        ])}
                      </Stack>
                    </>
                  )}
                </Section>
              </Grid>
            ))}
          </Grid>
          {present.length === 1 && (
            <Alert severity="info" sx={{ mt: 2 }}>
              Only {present[0].label} has been trained on this source. Train {MODELS.find((m) => m.key !== present[0].key).label} on
              the GNN page to compare the two.
            </Alert>
          )}
        </Box>
      )}
    </Box>
  )
}
