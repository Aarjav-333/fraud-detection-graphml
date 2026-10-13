import { Chip } from '@mui/material'

// The risk scale, shared by the computed risk level and the onboarding (KYC) category
export const RISK_LEVELS = ['Low', 'Medium', 'High']
const COLOR = { High: 'error', Medium: 'warning', Low: 'success' }

export default function RiskChip({ level }) {
  return <Chip size="small" label={level || 'Low'} color={COLOR[level] || 'default'} variant="outlined" />
}
