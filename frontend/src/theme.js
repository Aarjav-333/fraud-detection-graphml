import { createTheme } from '@mui/material/styles'

// Security-console palette: indigo/teal for actions, red/amber/green reserved for risk levels.
export const SIDEBAR_BG = '#0f172a'   // dark slate
export const SIDEBAR_FG = '#cbd5e1'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#4338ca' },   // indigo
    secondary: { main: '#0f766e' }, // teal
    background: { default: '#f5f6f8', paper: '#ffffff' },
    error: { main: '#dc2626' },     // High risk
    warning: { main: '#d97706' },   // Medium risk
    success: { main: '#16a34a' },   // Low risk
    text: { primary: '#111827', secondary: '#6b7280' },
  },
  typography: {
    fontFamily: 'Inter, system-ui, Roboto, Helvetica, Arial, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
  },
})
