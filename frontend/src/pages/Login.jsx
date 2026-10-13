import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Button, Typography, Alert, Stack, InputAdornment, IconButton, OutlinedInput,
  FormControl, FormLabel, FormHelperText, CircularProgress, Collapse,
} from '@mui/material'
import { keyframes } from '@emotion/react'
import ShieldIcon from '@mui/icons-material/Shield'
import PersonOutlineRoundedIcon from '@mui/icons-material/PersonOutlineRounded'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined'
import VisibilityOffOutlinedIcon from '@mui/icons-material/VisibilityOffOutlined'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded'
import ErrorOutlineRoundedIcon from '@mui/icons-material/ErrorOutlineRounded'
import HubOutlinedIcon from '@mui/icons-material/HubOutlined'
import RuleOutlinedIcon from '@mui/icons-material/RuleOutlined'
import NotificationsActiveOutlinedIcon from '@mui/icons-material/NotificationsActiveOutlined'
import VerifiedUserOutlinedIcon from '@mui/icons-material/VerifiedUserOutlined'
import { useAuth } from '../context/AuthContext'
import { SIDEBAR_BG } from '../theme'
import LoginNetworkBackdrop from '../components/LoginNetworkBackdrop'

// A hosted backend on a free tier can take a while to wake up; tell the user after this long.
const SLOW_LOGIN_MS = 6000

const BRAND_GRADIENT = 'linear-gradient(135deg, #4338ca 0%, #5b21b6 100%)'
const BRAND_GRADIENT_HOVER = 'linear-gradient(135deg, #4f46e5 0%, #6d28d9 100%)'
const EASE = 'cubic-bezier(0.2, 0.8, 0.2, 1)'

const fadeUp = keyframes`
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
`
const shakeX = keyframes`
  10%, 90% { transform: translateX(-1px); }
  20%, 80% { transform: translateX(3px); }
  30%, 50%, 70% { transform: translateX(-5px); }
  40%, 60% { transform: translateX(5px); }
`
const livePulse = keyframes`
  0%   { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.55); }
  70%  { box-shadow: 0 0 0 7px rgba(52, 211, 153, 0); }
  100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
`

// Entrance animation, skipped for users who prefer reduced motion.
const enter = (delay = 0) => ({
  '@media (prefers-reduced-motion: no-preference)': {
    animation: `${fadeUp} 0.6s ${EASE} ${delay}s both`,
  },
})

const FEATURES = [
  { icon: HubOutlinedIcon, title: 'Graph intelligence', text: 'Graph neural networks expose mule accounts and hidden fraud rings.' },
  { icon: RuleOutlinedIcon, title: 'Explainable detection', text: 'Every risk score is backed by the rules and signals that triggered it.' },
  { icon: NotificationsActiveOutlinedIcon, title: 'Real-time alerts', text: 'Analysts are notified the moment a flagged account transacts.' },
]

function BrandMark({ dark = false }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center">
      <Box
        sx={{
          width: 40, height: 40, borderRadius: '12px', display: 'grid', placeItems: 'center',
          background: BRAND_GRADIENT,
          boxShadow: '0 8px 20px -8px rgba(99, 102, 241, 0.8), inset 0 1px 0 rgba(255,255,255,0.18)',
        }}
      >
        <ShieldIcon sx={{ color: '#fff', fontSize: 22 }} />
      </Box>
      <Box>
        <Typography sx={{ fontWeight: 700, fontSize: 17, lineHeight: 1.15, color: dark ? '#fff' : '#0f172a', letterSpacing: '-0.01em' }}>
          FraudGraph
        </Typography>
        <Typography sx={{ fontSize: 12.5, fontWeight: 500, color: dark ? '#94a3b8' : '#64748b' }}>
          Detection Console
        </Typography>
      </Box>
    </Stack>
  )
}

function ShowcasePanel() {
  return (
    <Box
      component="aside"
      sx={{
        display: { xs: 'none', md: 'flex' },
        flex: { md: '1 1 52%', lg: '1 1 56%' },
        position: 'relative',
        overflow: 'hidden',
        flexDirection: 'column',
        justifyContent: 'space-between',
        px: { md: 6, lg: 8 },
        py: { md: 5, lg: 6 },
        color: '#e2e8f0',
        bgcolor: SIDEBAR_BG,
        backgroundImage: `
          radial-gradient(60% 50% at 80% 20%, rgba(99, 102, 241, 0.28) 0%, transparent 70%),
          radial-gradient(50% 45% at 10% 95%, rgba(91, 33, 182, 0.30) 0%, transparent 70%),
          linear-gradient(180deg, #0b1120 0%, ${SIDEBAR_BG} 100%)`,
      }}
    >
      {/* Faint grid, faded out toward the edges. */}
      <Box
        aria-hidden="true"
        sx={{
          position: 'absolute', inset: 0,
          backgroundImage: `
            linear-gradient(rgba(148, 163, 184, 0.07) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148, 163, 184, 0.07) 1px, transparent 1px)`,
          backgroundSize: '44px 44px',
          maskImage: 'radial-gradient(ellipse 80% 70% at 50% 40%, #000 30%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse 80% 70% at 50% 40%, #000 30%, transparent 100%)',
        }}
      />
      <LoginNetworkBackdrop sx={{ opacity: 0.85 }} />
      {/* Darken the lower-left so the copy stays legible over the graph. */}
      <Box
        aria-hidden="true"
        sx={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(115deg, rgba(11,17,32,0.92) 0%, rgba(11,17,32,0.7) 45%, rgba(11,17,32,0.1) 100%)',
        }}
      />

      <Box sx={{ position: 'relative', ...enter(0) }}>
        <BrandMark dark />
      </Box>

      <Box sx={{ position: 'relative', maxWidth: 520, my: 6 }}>
        <Box
          sx={{
            display: 'inline-flex', alignItems: 'center', gap: 1, px: 1.5, py: 0.6, mb: 3,
            borderRadius: 999, border: '1px solid rgba(129, 140, 248, 0.35)',
            bgcolor: 'rgba(67, 56, 202, 0.18)', backdropFilter: 'blur(6px)',
            fontSize: 12.5, fontWeight: 600, color: '#c7d2fe', letterSpacing: '0.02em',
            ...enter(0.08),
          }}
        >
          <Box
            sx={{
              width: 8, height: 8, borderRadius: '50%', bgcolor: '#34d399',
              '@media (prefers-reduced-motion: no-preference)': { animation: `${livePulse} 2s infinite` },
            }}
          />
          AI-powered fraud intelligence
        </Box>

        <Typography
          component="p"
          sx={{
            fontSize: { md: 36, lg: 44 }, fontWeight: 700, lineHeight: 1.12,
            letterSpacing: '-0.025em', color: '#f8fafc', mb: 2.5, ...enter(0.14),
          }}
        >
          Expose the{' '}
          <Box
            component="span"
            sx={{
              background: 'linear-gradient(90deg, #a5b4fc 0%, #c4b5fd 50%, #f9a8d4 100%)',
              WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            }}
          >
            networks
          </Box>{' '}
          behind financial fraud.
        </Typography>
        <Typography sx={{ fontSize: { md: 15.5, lg: 16.5 }, lineHeight: 1.65, color: '#94a3b8', maxWidth: 460, ...enter(0.2) }}>
          Graph analytics, machine learning and transparent rules work together to surface
          coordinated fraud before the money moves on.
        </Typography>

        <Stack component="ul" spacing={2.25} sx={{ listStyle: 'none', p: 0, m: 0, mt: 5 }}>
          {FEATURES.map(({ icon: Icon, title, text }, i) => (
            <Stack component="li" key={title} direction="row" spacing={2} alignItems="flex-start" sx={enter(0.28 + i * 0.07)}>
              <Box
                sx={{
                  flexShrink: 0, width: 38, height: 38, borderRadius: '10px', display: 'grid', placeItems: 'center',
                  bgcolor: 'rgba(99, 102, 241, 0.14)', border: '1px solid rgba(129, 140, 248, 0.25)', color: '#a5b4fc',
                }}
              >
                <Icon sx={{ fontSize: 20 }} />
              </Box>
              <Box>
                <Typography sx={{ fontWeight: 600, fontSize: 14.5, color: '#e2e8f0' }}>{title}</Typography>
                <Typography sx={{ fontSize: 13.5, color: '#94a3b8', lineHeight: 1.55 }}>{text}</Typography>
              </Box>
            </Stack>
          ))}
        </Stack>
      </Box>

      <Typography sx={{ position: 'relative', fontSize: 12.5, color: '#64748b', ...enter(0.5) }}>
        © {new Date().getFullYear()} FraudGraph · Graph ML fraud detection
      </Typography>
    </Box>
  )
}

const inputSx = {
  borderRadius: '12px',
  bgcolor: '#fff',
  fontSize: 15,
  transition: `box-shadow 0.2s ${EASE}, background-color 0.2s`,
  '& .MuiOutlinedInput-notchedOutline': { borderColor: '#e2e8f0', borderWidth: '1.5px', transition: 'border-color 0.2s' },
  '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#cbd5e1' },
  '&.Mui-focused': { boxShadow: '0 0 0 4px rgba(67, 56, 202, 0.14)' },
  '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'primary.main', borderWidth: '1.5px' },
  '&.Mui-error .MuiOutlinedInput-notchedOutline': { borderColor: 'error.main' },
  '&.Mui-error.Mui-focused': { boxShadow: '0 0 0 4px rgba(220, 38, 38, 0.14)' },
  '& .MuiInputAdornment-positionStart .MuiSvgIcon-root': { color: '#94a3b8', transition: 'color 0.2s' },
  '&.Mui-focused .MuiInputAdornment-positionStart .MuiSvgIcon-root': { color: 'primary.main' },
  '&.Mui-error .MuiInputAdornment-positionStart .MuiSvgIcon-root': { color: 'error.main' },
  '& input': { py: 1.6 },
  '& input::placeholder': { color: '#94a3b8', opacity: 1 },
  // Keep browser autofill from painting the field yellow/blue.
  '& input:-webkit-autofill': { WebkitBoxShadow: '0 0 0 100px #fff inset', WebkitTextFillColor: '#0f172a' },
}

// Labelled input with a leading icon and an optional message (error or warning) underneath.
function LoginField({ id, label, icon, message, tone = 'error', endAdornment, inputRef, inputProps, ...props }) {
  const helperId = `${id}-helper`
  return (
    <FormControl fullWidth required error={Boolean(message) && tone === 'error'}>
      <FormLabel
        htmlFor={id}
        sx={{
          mb: 0.9, fontSize: 13.5, fontWeight: 600, color: '#334155',
          '&.Mui-focused': { color: '#334155' },
          '&.Mui-error': { color: '#334155' },
          '& .MuiFormLabel-asterisk': { color: '#94a3b8' },
        }}
      >
        {label}
      </FormLabel>
      <OutlinedInput
        id={id}
        inputRef={inputRef}
        startAdornment={<InputAdornment position="start">{icon}</InputAdornment>}
        endAdornment={endAdornment}
        inputProps={{ ...inputProps, 'aria-describedby': message ? helperId : undefined }}
        sx={inputSx}
        {...props}
      />
      <Collapse in={Boolean(message)} unmountOnExit>
        <FormHelperText
          id={helperId}
          sx={{
            mx: 0.25, mt: 0.9, display: 'flex', alignItems: 'center', gap: 0.75, fontSize: 12.5, fontWeight: 500,
            color: tone === 'warning' ? '#b45309' : undefined,
          }}
        >
          {tone === 'warning'
            ? <WarningAmberRoundedIcon sx={{ fontSize: 16 }} />
            : <ErrorOutlineRoundedIcon sx={{ fontSize: 16 }} />}
          {message}
        </FormHelperText>
      </Collapse>
    </FormControl>
  )
}

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState({ username: false, password: false })
  const [capsLock, setCapsLock] = useState(false)
  const [slow, setSlow] = useState(false)
  const [shake, setShake] = useState(false)
  const usernameRef = useRef(null)
  const passwordRef = useRef(null)

  // Let the user know when a sign-in is taking unusually long (e.g. backend cold start).
  useEffect(() => {
    if (!busy) {
      setSlow(false)
      return undefined
    }
    const timer = setTimeout(() => setSlow(true), SLOW_LOGIN_MS)
    return () => clearTimeout(timer)
  }, [busy])

  const usernameError = touched.username && !username ? 'Enter your username.' : ''
  const passwordError = touched.password && !password ? 'Enter your password.' : ''

  async function handleSubmit(e) {
    e.preventDefault()
    // Both fields are required, as before; report it inline rather than with a browser bubble.
    if (!username || !password) {
      setTouched({ username: true, password: true })
      ;(username ? passwordRef : usernameRef).current?.focus()
      return
    }
    setError('')
    setBusy(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Login failed. Check your credentials.')
      setShake(true)
      passwordRef.current?.focus()
      passwordRef.current?.select()
    } finally {
      setBusy(false)
    }
  }

  function trackCapsLock(e) {
    if (typeof e.getModifierState === 'function') setCapsLock(e.getModifierState('CapsLock'))
  }

  const passwordMessage = passwordError || (capsLock ? 'Caps Lock is on.' : '')

  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh', display: 'flex', bgcolor: '#f8fafc',
        fontFeatureSettings: '"cv11", "ss01"',
      }}
    >
      <ShowcasePanel />

      <Box
        sx={{
          flex: { xs: '1 1 100%', md: '1 1 48%', lg: '1 1 44%' },
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative',
          px: { xs: 2, sm: 4, md: 6 },
          py: { xs: 4, sm: 6 },
          backgroundImage: {
            xs: 'radial-gradient(90% 45% at 50% 0%, rgba(99, 102, 241, 0.14) 0%, transparent 70%)',
            md: 'radial-gradient(70% 40% at 100% 0%, rgba(99, 102, 241, 0.08) 0%, transparent 70%)',
          },
        }}
      >
        <Box
          sx={{
            width: '100%', maxWidth: 420,
            p: { xs: 0, sm: 5, md: 0 },
            bgcolor: { xs: 'transparent', sm: '#fff', md: 'transparent' },
            borderRadius: { sm: '20px' },
            border: { sm: '1px solid #e2e8f0', md: 'none' },
            boxShadow: { sm: '0 24px 48px -24px rgba(15, 23, 42, 0.25)', md: 'none' },
            ...enter(0.05),
          }}
        >
          <Box
            onAnimationEnd={(e) => { if (e.target === e.currentTarget) setShake(false) }}
            sx={shake ? { '@media (prefers-reduced-motion: no-preference)': { animation: `${shakeX} 0.45s ${EASE} both` } } : undefined}
          >
            <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 4 }}>
              <BrandMark />
            </Box>

            <Typography
              component="h1"
              sx={{ fontSize: { xs: 26, sm: 28 }, fontWeight: 700, letterSpacing: '-0.02em', color: '#0f172a', mb: 1 }}
            >
              Welcome back
            </Typography>
            <Typography sx={{ fontSize: 15, color: '#64748b', mb: 4, lineHeight: 1.6 }}>
              Sign in to the FraudGraph console to continue your investigations.
            </Typography>

            <Collapse in={Boolean(error)} unmountOnExit>
              <Alert
                severity="error"
                variant="outlined"
                sx={{
                  mb: 3, borderRadius: '12px', bgcolor: '#fef2f2', borderColor: '#fecaca', color: '#991b1b',
                  alignItems: 'center', '& .MuiAlert-icon': { color: '#dc2626' },
                }}
              >
                {error}
              </Alert>
            </Collapse>

            <form onSubmit={handleSubmit} noValidate aria-busy={busy}>
              <Stack spacing={2.5}>
                <LoginField
                  id="login-username"
                  name="username"
                  label="Username"
                  placeholder="Enter your username"
                  autoComplete="username"
                  inputProps={{ autoCapitalize: 'none', spellCheck: false }}
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, username: true }))}
                  readOnly={busy}
                  inputRef={usernameRef}
                  icon={<PersonOutlineRoundedIcon fontSize="small" />}
                  message={usernameError}
                />
                <LoginField
                  id="login-password"
                  name="password"
                  label="Password"
                  placeholder="Enter your password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={trackCapsLock}
                  onKeyUp={trackCapsLock}
                  onBlur={() => {
                    setTouched((t) => ({ ...t, password: true }))
                    setCapsLock(false)
                  }}
                  readOnly={busy}
                  inputRef={passwordRef}
                  icon={<LockOutlinedIcon fontSize="small" />}
                  message={passwordMessage}
                  tone={passwordError ? 'error' : 'warning'}
                  endAdornment={(
                    <InputAdornment position="end">
                      <IconButton
                        edge="end"
                        size="small"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        aria-controls="login-password"
                        onClick={() => setShowPassword((s) => !s)}
                        onMouseDown={(e) => e.preventDefault()}
                        sx={{
                          color: '#64748b', mr: -0.25,
                          '&:hover': { color: 'primary.main', bgcolor: 'rgba(67, 56, 202, 0.08)' },
                          '&.Mui-focusVisible': { outline: '2px solid #818cf8', outlineOffset: 1 },
                        }}
                      >
                        {showPassword
                          ? <VisibilityOffOutlinedIcon fontSize="small" />
                          : <VisibilityOutlinedIcon fontSize="small" />}
                      </IconButton>
                    </InputAdornment>
                  )}
                />

                <Box sx={{ pt: 0.5 }}>
                  <Button
                    type="submit"
                    fullWidth
                    size="large"
                    disabled={busy}
                    endIcon={busy ? null : <ArrowForwardRoundedIcon />}
                    sx={{
                      py: 1.55,
                      borderRadius: '12px',
                      fontSize: 15.5,
                      color: '#fff',
                      position: 'relative',
                      overflow: 'hidden',
                      background: BRAND_GRADIENT,
                      boxShadow: '0 12px 24px -12px rgba(67, 56, 202, 0.75), inset 0 1px 0 rgba(255,255,255,0.15)',
                      transition: `transform 0.2s ${EASE}, box-shadow 0.2s ${EASE}`,
                      '& .MuiButton-endIcon': { transition: `transform 0.2s ${EASE}` },
                      // Light sheen that sweeps across on hover.
                      '&::after': {
                        content: '""', position: 'absolute', top: 0, bottom: 0, left: '-60%', width: '50%',
                        background: 'linear-gradient(100deg, transparent, rgba(255,255,255,0.22), transparent)',
                        transform: 'skewX(-20deg)', transition: `left 0.6s ${EASE}`, pointerEvents: 'none',
                      },
                      '&:hover': {
                        background: BRAND_GRADIENT_HOVER,
                        transform: 'translateY(-1px)',
                        boxShadow: '0 16px 30px -12px rgba(79, 70, 229, 0.8), inset 0 1px 0 rgba(255,255,255,0.15)',
                        '& .MuiButton-endIcon': { transform: 'translateX(3px)' },
                        '&::after': { left: '120%' },
                      },
                      '&:active': { transform: 'translateY(0)' },
                      '&.Mui-focusVisible': { outline: '3px solid #a5b4fc', outlineOffset: 2 },
                      '&.Mui-disabled': { color: '#fff', background: BRAND_GRADIENT, opacity: 0.85, boxShadow: 'none' },
                      '@media (prefers-reduced-motion: reduce)': {
                        transition: 'none',
                        '&:hover': { transform: 'none' },
                        '&::after': { display: 'none' },
                      },
                    }}
                  >
                    {busy ? (
                      <>
                        <CircularProgress size={18} thickness={5} sx={{ color: 'inherit', mr: 1.25 }} aria-hidden="true" />
                        Verifying credentials…
                      </>
                    ) : 'Sign in'}
                  </Button>
                </Box>

                <Collapse in={slow} unmountOnExit>
                  <Typography role="status" sx={{ fontSize: 13, color: '#64748b', textAlign: 'center', lineHeight: 1.55 }}>
                    Still working — the server may be waking up, which can take a minute.
                  </Typography>
                </Collapse>
              </Stack>
            </form>

            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              justifyContent="center"
              sx={{ mt: 4, pt: 3, borderTop: '1px solid #e2e8f0', color: '#64748b' }}
            >
              <VerifiedUserOutlinedIcon sx={{ fontSize: 16, color: '#0f766e' }} />
              <Typography sx={{ fontSize: 12.5 }}>
                Restricted access · ask your admin for an account
              </Typography>
            </Stack>
          </Box>
        </Box>
      </Box>
    </Box>
  )
}
