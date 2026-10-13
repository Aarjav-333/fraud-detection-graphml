import { useNavigate } from 'react-router-dom'
import { Alert, AlertTitle, Box, Button, CircularProgress, Typography } from '@mui/material'
import ScienceIcon from '@mui/icons-material/Science'
import { useSystem } from '../context/SystemContext'

// ML and GNN pages train and evaluate models on the main labelled dataset. In the
// standalone demo (22 scripted accounts) they explain why they're off instead.
// Nothing renders until it's known which backend this is, so they never start up there.
export default function RequiresMainDataset({ title, children }) {
  const { loaded, standalone, mlUnavailableReason } = useSystem()
  const navigate = useNavigate()
  if (!loaded) return <Box sx={{ display: 'flex', justifyContent: 'center', pt: 8 }}><CircularProgress /></Box>
  if (!standalone) return children
  return (
    <Box>
      <Typography variant="h4">{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Standalone Demo Mode</Typography>
      <Alert severity="info" icon={<ScienceIcon />}
        action={<Button color="inherit" size="small" sx={{ whiteSpace: 'nowrap' }} onClick={() => navigate('/demo')}>Open the scenario</Button>}>
        <AlertTitle>Not available in the standalone demo</AlertTitle>
        {mlUnavailableReason}
        <Box sx={{ mt: 1 }}>
          To use {title}, run the normal backend on the main dataset, or the full demo copy
          (<Box component="code" sx={{ fontFamily: 'monospace' }}>python -m scripts.demo_scenario --serve</Box>).
        </Box>
      </Alert>
    </Box>
  )
}
