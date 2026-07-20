import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Paper, TextField, Button, Typography, Alert, Stack, InputAdornment,
} from '@mui/material'
import ShieldIcon from '@mui/icons-material/Shield'
import PersonIcon from '@mui/icons-material/Person'
import LockIcon from '@mui/icons-material/Lock'
import { useAuth } from '../context/AuthContext'
import { SIDEBAR_BG } from '../theme'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Login failed. Check your credentials.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: SIDEBAR_BG, p: 2 }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 400 }} elevation={6}>
        <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <ShieldIcon sx={{ fontSize: 40, color: 'primary.main' }} />
          <Typography variant="h5">FraudGraph Console</Typography>
          <Typography variant="body2" color="text.secondary">Sign in to continue</Typography>
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <Stack spacing={2.5}>
            <TextField
              label="Username" value={username} onChange={(e) => setUsername(e.target.value)}
              fullWidth required autoFocus
              InputProps={{ startAdornment: <InputAdornment position="start"><PersonIcon fontSize="small" /></InputAdornment> }}
            />
            <TextField
              label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              fullWidth required
              InputProps={{ startAdornment: <InputAdornment position="start"><LockIcon fontSize="small" /></InputAdornment> }}
            />
            <Button type="submit" variant="contained" size="large" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  )
}
