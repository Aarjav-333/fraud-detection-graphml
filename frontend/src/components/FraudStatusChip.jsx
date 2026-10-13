import { Chip } from '@mui/material'
import GppBadIcon from '@mui/icons-material/GppBad'
import ManageSearchIcon from '@mui/icons-material/ManageSearch'
import ReportProblemOutlinedIcon from '@mui/icons-material/ReportProblemOutlined'
import VerifiedUserOutlinedIcon from '@mui/icons-material/VerifiedUserOutlined'

// The account's fraud status: Suspicious comes from the rules / ML score,
// Under Review and Confirmed Fraud only from an analyst.
const STYLE = {
  Normal: { color: 'default', variant: 'outlined', icon: <VerifiedUserOutlinedIcon /> },
  Suspicious: { color: 'warning', variant: 'outlined', icon: <ReportProblemOutlinedIcon /> },
  'Under Review': { color: 'info', variant: 'filled', icon: <ManageSearchIcon /> },
  'Confirmed Fraud': { color: 'error', variant: 'filled', icon: <GppBadIcon /> },
}

export const FRAUD_STATUSES = Object.keys(STYLE)

export default function FraudStatusChip({ status, size = 'small' }) {
  const style = STYLE[status] || STYLE.Normal
  return <Chip size={size} label={status || 'Normal'} color={style.color} variant={style.variant} icon={style.icon} />
}
