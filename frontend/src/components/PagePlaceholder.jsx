import { Box, Paper, Typography } from '@mui/material'

export default function PagePlaceholder({ title, phase, description }) {
  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 0.5 }}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>{description}</Typography>
      <Paper sx={{ p: 4, border: '1px dashed #cbd5e1', textAlign: 'center', color: 'text.secondary' }}>
        <Typography>This module will be built in {phase}.</Typography>
      </Paper>
    </Box>
  )
}
