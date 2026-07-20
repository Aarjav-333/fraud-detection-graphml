import { Chip } from '@mui/material'

const COLOR = { High: 'error', Medium: 'warning', Low: 'success' }

export default function RiskChip({ level }) {
  return <Chip size="small" label={level || 'Low'} color={COLOR[level] || 'default'} variant="outlined" />
}
