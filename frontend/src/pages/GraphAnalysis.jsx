import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Box, Typography, Paper, Grid, Button, Stack, Chip, CircularProgress, Alert,
  Table, TableHead, TableBody, TableRow, TableCell, TextField, MenuItem,
  InputAdornment, LinearProgress, ToggleButtonGroup, ToggleButton,
} from '@mui/material'
import HubIcon from '@mui/icons-material/Hub'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import SearchIcon from '@mui/icons-material/Search'
import ForceGraph2D from 'react-force-graph-2d'
import { getGraphStatus, runGraphAnalysis, getGraphMetrics, getNeighborhood } from '../api/graph'

const RISK_COLOR = { High: '#dc2626', Medium: '#d97706', Low: '#16a34a' }
const money = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })

export default function GraphAnalysis() {
  const [status, setStatus] = useState(null)
  const [summary, setSummary] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const [sortBy, setSortBy] = useState('pagerank')
  const [rows, setRows] = useState([])
  const [loadingRows, setLoadingRows] = useState(false)

  const [uid, setUid] = useState('')
  const [hops, setHops] = useState(1)
  const [graphData, setGraphData] = useState(null)
  const [graphError, setGraphError] = useState('')
  const [loadingGraph, setLoadingGraph] = useState(false)
  const graphBoxRef = useRef(null)
  const [graphWidth, setGraphWidth] = useState(600)

  useEffect(() => { getGraphStatus().then(setStatus).catch(() => {}) }, [])

  const loadRows = useCallback(async () => {
    if (!status?.has_run) return
    setLoadingRows(true)
    try { setRows(await getGraphMetrics({ sortBy, limit: 15 })) }
    finally { setLoadingRows(false) }
  }, [sortBy, status])

  useEffect(() => { loadRows() }, [loadRows])

  useEffect(() => {
    const measure = () => {
      if (graphBoxRef.current) setGraphWidth(graphBoxRef.current.offsetWidth - 4)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [graphData])

  async function handleRun() {
    setRunning(true); setError('')
    try {
      const res = await runGraphAnalysis()
      setSummary(res)
      setStatus({ has_run: true, accounts_analyzed: res.nodes })
    } catch (err) {
      setError(err?.response?.data?.detail || 'Graph analysis failed — is the backend running?')
    } finally { setRunning(false) }
  }

  async function loadNeighborhood(centerUid, h = hops) {
    if (!centerUid) return
    setLoadingGraph(true); setGraphError(''); setGraphData(null)
    try {
      const data = await getNeighborhood(centerUid.trim(), h)
      setGraphData(data)
    } catch (err) {
      setGraphError(err?.response?.status === 404
        ? `Account '${centerUid.trim()}' was not found in the graph.`
        : 'Could not load the neighborhood.')
    } finally { setLoadingGraph(false) }
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4">Graph Analysis</Typography>
          <Typography variant="body2" color="text.secondary">
            Transaction network: accounts = nodes, transactions = edges (workflow Steps 7–8)
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={handleRun} disabled={running}>
          {running ? 'Analyzing…' : 'Build & analyze graph'}
        </Button>
      </Stack>

      {running && <Paper sx={{ p: 3, mb: 3 }}><Typography variant="body2" sx={{ mb: 1 }}>
        Building the network and computing centrality, PageRank, components, communities and cycles…
      </Typography><LinearProgress /></Paper>}
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {summary && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {[
            ['Nodes (accounts)', summary.nodes], ['Edges (relations)', summary.edges],
            ['Components', summary.components], ['Communities', summary.communities],
            ['Money cycles', summary.cycles_found], ['Accounts in cycles', summary.accounts_in_cycles],
          ].map(([label, value]) => (
            <Grid item xs={6} sm={4} md={2} key={label}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h5">{Number(value).toLocaleString('en-IN')}</Typography>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {status?.has_run ? (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="h6">Top accounts by graph importance</Typography>
              <TextField select size="small" value={sortBy} onChange={(e) => setSortBy(e.target.value)} sx={{ width: 220 }}>
                <MenuItem value="pagerank">PageRank</MenuItem>
                <MenuItem value="degree_centrality">Degree centrality</MenuItem>
                <MenuItem value="in_degree">In-degree (receivers)</MenuItem>
                <MenuItem value="out_degree">Out-degree (senders)</MenuItem>
                <MenuItem value="total_received">Total received</MenuItem>
                <MenuItem value="total_sent">Total sent</MenuItem>
              </TextField>
            </Stack>
            {loadingRows ? <LinearProgress /> : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Account</TableCell>
                    <TableCell align="right">PageRank</TableCell>
                    <TableCell align="right">In / Out</TableCell>
                    <TableCell align="right">Received</TableCell>
                    <TableCell align="right">Sent</TableCell>
                    <TableCell align="center">In cycle?</TableCell>
                    <TableCell align="right">Community</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.account_uid} hover>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{r.account_uid}</TableCell>
                      <TableCell align="right">{r.pagerank.toFixed(6)}</TableCell>
                      <TableCell align="right">{r.in_degree} / {r.out_degree}</TableCell>
                      <TableCell align="right">{money(r.total_received)}</TableCell>
                      <TableCell align="right">{money(r.total_sent)}</TableCell>
                      <TableCell align="center">
                        {r.in_cycle
                          ? <Chip size="small" label="Yes" color="warning" />
                          : <Chip size="small" label="No" variant="outlined" />}
                      </TableCell>
                      <TableCell align="right">#{r.community_id} ({r.community_size})</TableCell>
                      <TableCell align="right">
                        <Button size="small" onClick={() => { setUid(r.account_uid); loadNeighborhood(r.account_uid) }}>
                          View network
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Neighborhood explorer</Typography>
            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
              <TextField
                size="small" placeholder="Account UID e.g. ACC01210" value={uid}
                onChange={(e) => setUid(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadNeighborhood(uid)}
                sx={{ width: 280 }}
                InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
              />
              <ToggleButtonGroup size="small" exclusive value={hops}
                onChange={(e, v) => { if (v) { setHops(v); if (graphData) loadNeighborhood(uid, v) } }}>
                <ToggleButton value={1}>1 hop</ToggleButton>
                <ToggleButton value={2}>2 hops</ToggleButton>
              </ToggleButtonGroup>
              <Button variant="outlined" startIcon={<HubIcon />} onClick={() => loadNeighborhood(uid)}>
                Show network
              </Button>
            </Stack>
            {graphError && <Alert severity="warning" sx={{ mb: 2 }}>{graphError}</Alert>}
            {loadingGraph && <LinearProgress sx={{ mb: 2 }} />}
            {graphData && (
              <Box ref={graphBoxRef}
                sx={{ border: '1px solid #e5e7eb', borderRadius: 2, overflow: 'hidden', bgcolor: '#0f172a' }}>
                <ForceGraph2D
                  graphData={{ nodes: graphData.nodes, links: graphData.links }}
                  width={graphWidth} height={440}
                  backgroundColor="#0f172a"
                  nodeLabel={(n) => `${n.id} · ${n.name} (${n.risk} risk)`}
                  nodeCanvasObject={(node, ctx, scale) => {
                    const r = node.is_center ? 8 : 5
                    ctx.beginPath()
                    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
                    ctx.fillStyle = node.is_center ? '#818cf8' : (RISK_COLOR[node.risk] || '#64748b')
                    ctx.fill()
                    if (node.is_center || scale > 2) {
                      ctx.font = `${10 / scale}px Inter`
                      ctx.fillStyle = '#cbd5e1'
                      ctx.textAlign = 'center'
                      ctx.fillText(node.id, node.x, node.y - r - 2 / scale)
                    }
                  }}
                  linkColor={() => 'rgba(148,163,184,0.35)'}
                  linkDirectionalArrowLength={4}
                  linkDirectionalArrowRelPos={1}
                  linkWidth={(l) => Math.min(1 + Math.log10(1 + l.amount / 10000), 4)}
                  linkLabel={(l) => `₹${Number(l.amount).toLocaleString('en-IN')} in ${l.count} txn(s)`}
                  cooldownTicks={80}
                />
                <Stack direction="row" spacing={2} sx={{ p: 1.5, bgcolor: '#1e293b' }}>
                  <Chip size="small" sx={{ bgcolor: '#818cf8', color: '#fff' }} label="Center account" />
                  <Chip size="small" sx={{ bgcolor: RISK_COLOR.High, color: '#fff' }} label="High risk" />
                  <Chip size="small" sx={{ bgcolor: RISK_COLOR.Medium, color: '#fff' }} label="Medium risk" />
                  <Chip size="small" sx={{ bgcolor: RISK_COLOR.Low, color: '#fff' }} label="Low risk" />
                </Stack>
              </Box>
            )}
            {!graphData && !loadingGraph && !graphError && (
              <Typography variant="body2" color="text.secondary">
                Enter an account UID (or click "View network" on a top account above) to see its money flows.
                Arrows show direction; thicker lines mean more money.
              </Typography>
            )}
          </Paper>
        </>
      ) : !running && (
        <Alert severity="info">Click <b>Build & analyze graph</b> to construct the transaction network and compute graph metrics.</Alert>
      )}
    </Box>
  )
}
