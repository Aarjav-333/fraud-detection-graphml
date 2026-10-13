import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, CssBaseline } from '@mui/material'
import { theme } from './theme'
import { AuthProvider } from './context/AuthContext'
import { SystemProvider } from './context/SystemContext'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <SystemProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </SystemProvider>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
)
