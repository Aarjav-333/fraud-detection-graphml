import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert, LinearProgress,
  Table, TableContainer, TableHead, TableBody, TableRow, TableCell, TablePagination,
} from '@mui/material'
import GroupsIcon from '@mui/icons-material/Groups'
import RadarIcon from '@mui/icons-material/Radar'
import RiskChip from '../components/RiskChip'
import MoneyFlowGraph from '../components/MoneyFlowGraph'
import { useSystem } from '../context/SystemContext'
import { getRingsStatus, detectRings, getRing } from '../api/rings'

const ROLE_COLOR = { main: '#dc2626', withdrawal: '#7c3aed', source: '#d97706' }
const ROLE_LABEL = { main: 'Main (receiver)', withdrawal: 'Withdrawal', source: 'Source' }
const money = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })

export default function FraudRings() {
  const [status, setStatus] = useState(null)
  const [detecting, setDetecting] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState(null)   // full ring with nodes/links
  const [loadingRing, setLoadingRing] = useState(false)
  const { standalone, hasModelScores, modelScore } = useSystem()

  useEffect(() => { getRingsStatus().then(setStatus).catch(() => {}) }, [])

  async function handleDetect() {
    setDetecting(true); setError(''); setSelected(null)
    try {
      await detectRings()
      setStatus(await getRingsStatus())
    } catch (err) {
      setError(err?.response?.data?.detail || 'Detection failed — run Rule Detection and ML Scoring first.')
    } finally { setDetecting(false) }
  }

  async function openRing(ringId) {
    setLoadingRing(true)
    try { setSelected(await getRing(ringId)) }
    finally { setLoadingRing(false) }
  }

  const rings = status?.rings || []
  const pageRings = rings.slice(page * 10, page * 10 + 10)

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Fraud Rings</Typography>
          <Typography variant="body2" color="text.secondary">
            Connected groups of suspicious accounts moving money together (workflow Step 12)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<RadarIcon />} onClick={handleDetect} disabled={detecting}>
          {detecting ? 'Detecting…' : 'Detect fraud rings'}
        </Button>
      </Stack>

      {detecting && <Paper sx={{ p: 3, mb: 3 }}><LinearProgress /></Paper>}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {status?.has_run && (
        <>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {[
              ['Rings detected', status.rings_found],
              ['Accounts involved', status.accounts_involved],
              ['High-risk rings', status.high_risk_rings],
              ['Total money flow', money(status.total_flow)],
            ].map(([label, value]) => (
              <Grid item xs={6} md={3} key={label}>
                <Paper sx={{ p: 2, textAlign: 'center' }}>
                  <Typography variant="h5">{typeof value === 'number' ? value.toLocaleString('en-IN') : value}</Typography>
                  <Typography variant="caption" color="text.secondary">{label}</Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>

          <Grid container spacing={2}>
            <Grid item xs={12} lg={selected ? 5 : 12}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Detected rings</Typography>
                <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Ring</TableCell>
                      <TableCell align="right">Size</TableCell>
                      <TableCell>Main account</TableCell>
                      <TableCell align="right">Money flow</TableCell>
                      <TableCell align="right">ML score</TableCell>
                      <TableCell>Rules fired</TableCell>
                      <TableCell>Risk</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {pageRings.map((r) => (
                      <TableRow key={r.ring_id} hover selected={selected?.ring_id === r.ring_id}>
                        <TableCell sx={{ fontFamily: 'monospace' }}>{r.ring_id}</TableCell>
                        <TableCell align="right">{r.size}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace' }}>{r.main_account}</TableCell>
                        <TableCell align="right">{money(r.total_flow)}</TableCell>
                        <TableCell align="right">{modelScore(r.avg_fraud_score, 0)}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>
                          {r.rules == null ? '—' : (r.rules.join(' ') || 'none')}
                        </TableCell>
                        <TableCell><RiskChip level={r.risk} /></TableCell>
                        <TableCell align="right">
                          <Button size="small" startIcon={<GroupsIcon />} onClick={() => openRing(r.ring_id)}>
                            View
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </TableContainer>
                <TablePagination
                  component="div" count={rings.length} page={page} rowsPerPage={10}
                  rowsPerPageOptions={[10]} onPageChange={(e, p) => setPage(p)}
                />
                <Typography variant="caption" color="text.secondary">
                  Risk uses the stronger signal: the members' average ML score, or how many different
                  rules fired on the ring's own transactions (1 rule Low, 2 Medium, 3+ High).
                </Typography>
              </Paper>
            </Grid>

            {selected && (
              <Grid item xs={12} lg={7}>
                <Paper sx={{ p: 2 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="h6">
                      {selected.ring_id} — {selected.size} accounts, {money(selected.total_flow)} moved
                    </Typography>
                    <RiskChip level={selected.risk} />
                  </Stack>
                  {loadingRing ? <LinearProgress /> : (
                    <MoneyFlowGraph
                      nodes={selected.nodes} links={selected.links}
                      colorOf={(n) => ROLE_COLOR[n.role]}
                      radiusOf={(n) => (n.role === 'main' ? 10 : n.role === 'withdrawal' ? 8 : 5)}
                      showLabel={(n, scale) => n.role !== 'source' || scale > 2.2}
                      nodeTitle={(n) => `${n.id} · ${n.name}
role: ${ROLE_LABEL[n.role]}
`
                        + `${hasModelScores ? `score ${modelScore(n.fraud_score, 0)} · ` : ''}received ${money(n.received)} · sent ${money(n.sent)}`}
                      legend={[
                        { label: 'Main (receiver)', color: ROLE_COLOR.main },
                        { label: 'Withdrawal', color: ROLE_COLOR.withdrawal },
                        { label: 'Source accounts', color: ROLE_COLOR.source },
                      ]}
                    />
                  )}
                </Paper>
              </Grid>
            )}
          </Grid>
        </>
      )}

      {!status?.has_run && !detecting && (
        <Alert severity="info">
          {standalone
            ? <>Run <b>Rule Detection</b> first, then click <b>Detect fraud rings</b>.</>
            : <>Run <b>Rule Detection</b> and <b>ML Scoring</b> first, then click <b>Detect fraud rings</b>.</>}
        </Alert>
      )}
    </Box>
  )
}
