import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Chip, Stack, Typography } from '@mui/material'
import ForceGraph2D from 'react-force-graph-2d'
import { money } from '../utils/format'

// The money-flow network used for fraud rings and the demo scenario: accounts are
// nodes, money moves along directed edges (the moving dots show its direction).
//   colorOf / radiusOf / labelOf(node), showLabel(node, zoom) - how nodes are drawn
//   nodeTitle(node) - the hover text; legend - [{ label, color }]
export default function MoneyFlowGraph({
  nodes, links, colorOf, radiusOf, labelOf = (n) => n.id, showLabel = () => true,
  nodeTitle, legend = [], height = 430,
}) {
  const boxRef = useRef(null)
  const graphRef = useRef(null)
  const fitted = useRef(false)   // zoom to fit once per graph, not again after every drag
  const placed = useRef(new Map())   // id -> the node as last laid out
  const [width, setWidth] = useState(600)

  // The graph restarts its layout whenever it gets new data, so only give it new data
  // when the content changes (not on every re-render of the page around it), and then
  // keep the accounts it already placed where they are.
  const content = JSON.stringify([nodes, links])
  const graphData = useMemo(() => {
    const data = {
      nodes: nodes.map((n) => {
        const old = placed.current.get(n.id)
        return old ? { ...n, x: old.x, y: old.y, vx: old.vx, vy: old.vy } : { ...n }
      }),
      links: links.map((l) => ({ ...l })),   // copies: the graph replaces source/target with nodes
    }
    placed.current = new Map(data.nodes.map((n) => [n.id, n]))
    return data
  }, [content])   // the content, not the arrays' identity

  useEffect(() => { fitted.current = false }, [graphData])

  useEffect(() => {
    const measure = () => boxRef.current && setWidth(boxRef.current.offsetWidth - 4)
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  return (
    <Box ref={boxRef} sx={{ border: '1px solid #e5e7eb', borderRadius: 2, overflow: 'hidden', bgcolor: '#0f172a' }}>
      <ForceGraph2D
        ref={graphRef}
        onEngineStop={() => {
          if (!fitted.current && graphRef.current) {
            fitted.current = true
            graphRef.current.zoomToFit(400, 40)
          }
        }}
        graphData={graphData}
        width={width} height={height}
        backgroundColor="#0f172a"
        nodeLabel={nodeTitle}
        nodeCanvasObject={(node, ctx, scale) => {
          const r = radiusOf(node)
          ctx.beginPath()
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
          ctx.fillStyle = colorOf(node) || '#64748b'
          ctx.fill()
          if (showLabel(node, scale)) {
            ctx.font = `${10 / scale}px Inter`
            ctx.fillStyle = '#cbd5e1'
            ctx.textAlign = 'center'
            ctx.fillText(labelOf(node), node.x, node.y - r - 2 / scale)
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
      <Stack direction="row" spacing={2} sx={{ p: 1.5, bgcolor: '#1e293b', flexWrap: 'wrap' }} useFlexGap>
        {legend.map((item) => (
          <Chip key={item.label} size="small" sx={{ bgcolor: item.color, color: '#fff' }} label={item.label} />
        ))}
        <Typography variant="caption" sx={{ color: '#94a3b8', alignSelf: 'center' }}>
          Moving dots show money direction
        </Typography>
      </Stack>
    </Box>
  )
}
