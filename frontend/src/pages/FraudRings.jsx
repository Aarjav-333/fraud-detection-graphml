import { useEffect, useState, useRef } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, Alert, LinearProgress,
  Table, TableHead, TableBody, TableRow, TableCell, TablePagination,
} from '@mui/material'
import GroupsIcon from '@mui/icons-material/Groups'
import RadarIcon from '@mui/icons-material/Radar'
import ForceGraph2D from 'react-force-graph-2d'
import RiskChip from '../components/RiskChip'
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
  const graphBoxRef = useRef(null)
  const [graphWidth, setGraphWidth] = useState(600)

  useEffect(() => { getRingsStatus().then(setStatus).catch(() => {}) }, [])
  useEffect(() => {
    const measure = () => graphBoxRef.current && setGraphWidth(graphBoxRef.current.offsetWidth - 4)
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [selected])

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
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Ring</TableCell>
                      <TableCell align="right">Size</TableCell>
                      <TableCell>Main account</TableCell>
                      <TableCell align="right">Money flow</TableCell>
                      <TableCell align="right">Avg score</TableCell>
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
                        <TableCell align="right">{(r.avg_fraud_score * 100).toFixed(0)}%</TableCell>
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
                <TablePagination
                  component="div" count={rings.length} page={page} rowsPerPage={10}
                  rowsPerPageOptions={[10]} onPageChange={(e, p) => setPage(p)}
                />
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
                    <Box ref={graphBoxRef}
                      sx={{ border: '1px solid #e5e7eb', borderRadius: 2, overflow: 'hidden', bgcolor: '#0f172a' }}>
                      <ForceGraph2D
                        graphData={{ nodes: selected.nodes.map(n => ({ ...n })), links: selected.links.map(l => ({ ...l })) }}
                        width={graphWidth} height={430}
                        backgroundColor="#0f172a"
                        nodeLabel={(n) => `${n.id} · ${n.name}\nrole: ${ROLE_LABEL[n.role]}\nscore ${(n.fraud_score * 100).toFixed(0)}% · received ${money(n.received)} · sent ${money(n.sent)}`}
                        nodeCanvasObject={(node, ctx, scale) => {
                          const r = node.role === 'main' ? 10 : node.role === 'withdrawal' ? 8 : 5
                          ctx.beginPath()
                          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
                          ctx.fillStyle = ROLE_COLOR[node.role] || '#64748b'
                          ctx.fill()
                          if (node.role !== 'source' || scale > 2.2) {
                            ctx.font = `${10 / scale}px Inter`
                            ctx.fillStyle = '#cbd5e1'
                            ctx.textAlign = 'center'
                            ctx.fillText(node.id, node.x, node.y - r - 2 / scale)
                          }
                        }}
                        linkColor={() => 'rgba(148,163,184,0.4)'}
                        linkDirectionalArrowLength={4.5}
                        linkDirectionalArrowRelPos={1}
                        linkDirectionalParticles={2}
                        linkDirectionalParticleSpeed={0.004}
                        linkWidth={(l) => Math.min(1 + Math.log10(1 + l.amount / 10000), 4)}
                        linkLabel={(l) => `${money(l.amount)} in ${l.count} txn(s)`}
                        cooldownTicks={90}
                      />
                      <Stack direction="row" spacing={2} sx={{ p: 1.5, bgcolor: '#1e293b', flexWrap: 'wrap' }}>
                        <Chip size="small" sx={{ bgcolor: ROLE_COLOR.main, color: '#fff' }} label="Main (receiver)" />
                        <Chip size="small" sx={{ bgcolor: ROLE_COLOR.withdrawal, color: '#fff' }} label="Withdrawal" />
                        <Chip size="small" sx={{ bgcolor: ROLE_COLOR.source, color: '#fff' }} label="Source accounts" />
                        <Typography variant="caption" sx={{ color: '#94a3b8', alignSelf: 'center' }}>
                          Moving dots show money direction
                        </Typography>
                      </Stack>
                    </Box>
                  )}
                </Paper>
              </Grid>
            )}
          </Grid>
        </>
      )}

      {!status?.has_run && !detecting && (
        <Alert severity="info">
          Run <b>Rule Detection</b> and <b>ML Scoring</b> first, then click <b>Detect fraud rings</b>.
        </Alert>
      )}
    </Box>
  )
}
