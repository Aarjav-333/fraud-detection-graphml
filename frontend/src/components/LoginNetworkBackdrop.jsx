import { Box } from '@mui/material'
import { keyframes } from '@emotion/react'

// Decorative transaction network for the login screen: ordinary accounts in slate/indigo,
// plus one red cycle standing in for a detected fraud ring. Purely visual (aria-hidden).

const flow = keyframes`
  to { stroke-dashoffset: -40; }
`
const pulse = keyframes`
  0%   { transform: scale(1);   opacity: 0.55; }
  70%  { transform: scale(2.6); opacity: 0; }
  100% { transform: scale(2.6); opacity: 0; }
`
const twinkle = keyframes`
  0%, 100% { opacity: 0.35; }
  50%      { opacity: 0.9; }
`

const ACCOUNTS = [
  [60, 90], [200, 60], [330, 140], [150, 230], [460, 70], [760, 110], [740, 420],
  [520, 400], [300, 330], [90, 400], [220, 500], [420, 560], [650, 600], [760, 720],
  [540, 760], [330, 700], [120, 640], [60, 820], [250, 850], [470, 880], [700, 860],
]

const RING_CENTER = [600, 250]
const RING_RADIUS = 72
const RING = Array.from({ length: 5 }, (_, i) => {
  const a = (i / 5) * Math.PI * 2 - Math.PI / 2
  return [RING_CENTER[0] + RING_RADIUS * Math.cos(a), RING_CENTER[1] + RING_RADIUS * Math.sin(a)]
})

const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1])

// Link every account to its two nearest neighbours (deduplicated).
const ACCOUNT_EDGES = (() => {
  const seen = new Set()
  const edges = []
  ACCOUNTS.forEach((p, i) => {
    ACCOUNTS
      .map((q, j) => [j, dist(p, q)])
      .filter(([j]) => j !== i)
      .sort((x, y) => x[1] - y[1])
      .slice(0, 2)
      .forEach(([j]) => {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`
        if (!seen.has(key)) {
          seen.add(key)
          edges.push([ACCOUNTS[i], ACCOUNTS[j]])
        }
      })
  })
  return edges
})()

const RING_EDGES = RING.map((p, i) => [p, RING[(i + 1) % RING.length]])

// Feeder accounts paying into the ring.
const FEEDER_EDGES = [[ACCOUNTS[4], RING[0]], [ACCOUNTS[7], RING[3]], [ACCOUNTS[6], RING[2]]]

export default function LoginNetworkBackdrop({ sx }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 800 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
      sx={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        '& .flow': { strokeDasharray: '4 6' },
        '& .halo': { transformBox: 'fill-box', transformOrigin: 'center' },
        '@media (prefers-reduced-motion: no-preference)': {
          '& .flow': { animation: `${flow} 5s linear infinite` },
          '& .flow.fast': { animationDuration: '1.6s' },
          '& .halo': { animation: `${pulse} 2.8s ease-out infinite` },
          '& .twinkle': { animation: `${twinkle} 4s ease-in-out infinite` },
        },
        ...sx,
      }}
    >
      <defs>
        <radialGradient id="login-ring-glow">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
        </radialGradient>
      </defs>

      <g stroke="#6366f1" strokeWidth="1.2" fill="none">
        {ACCOUNT_EDGES.map(([p, q], i) => (
          <line
            key={i}
            x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]}
            className={i % 3 === 0 ? 'flow' : undefined}
            strokeOpacity={i % 3 === 0 ? 0.55 : 0.22}
          />
        ))}
      </g>

      <circle cx={RING_CENTER[0]} cy={RING_CENTER[1]} r={RING_RADIUS * 2} fill="url(#login-ring-glow)" />

      <g stroke="#f87171" strokeWidth="1.4" fill="none">
        {FEEDER_EDGES.map(([p, q], i) => (
          <line key={i} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} className="flow" strokeOpacity="0.45" />
        ))}
        {RING_EDGES.map(([p, q], i) => (
          <line key={i} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} className="flow fast" strokeOpacity="0.9" strokeWidth="2" />
        ))}
      </g>

      <g>
        {ACCOUNTS.map(([x, y], i) => (
          <circle
            key={i}
            cx={x} cy={y} r={i % 4 === 0 ? 5 : 3.5}
            fill={i % 4 === 0 ? '#818cf8' : '#94a3b8'}
            className="twinkle"
            style={{ animationDelay: `${(i * 0.37) % 4}s` }}
          />
        ))}
      </g>

      <g>
        {RING.map(([x, y], i) => (
          <g key={i}>
            <circle
              cx={x} cy={y} r="7" fill="#ef4444" className="halo"
              style={{ animationDelay: `${i * 0.45}s` }}
            />
            <circle cx={x} cy={y} r="6" fill="#ef4444" stroke="#fecaca" strokeWidth="1.5" />
          </g>
        ))}
      </g>
    </Box>
  )
}
