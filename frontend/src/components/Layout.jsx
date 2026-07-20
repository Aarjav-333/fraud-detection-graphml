import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  AppBar, Box, Drawer, List, ListItemButton, ListItemIcon, ListItemText,
  Toolbar, Typography, Divider, Avatar, Button, Chip,
} from '@mui/material'
import DashboardIcon from '@mui/icons-material/Dashboard'
import PeopleIcon from '@mui/icons-material/People'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import GavelIcon from '@mui/icons-material/Gavel'
import HubIcon from '@mui/icons-material/Hub'
import TableChartIcon from '@mui/icons-material/TableChart'
import ModelTrainingIcon from '@mui/icons-material/ModelTraining'
import PsychologyIcon from '@mui/icons-material/Psychology'
import GroupsIcon from '@mui/icons-material/Groups'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import FolderSharedIcon from '@mui/icons-material/FolderShared'
import AssessmentIcon from '@mui/icons-material/Assessment'
import ShieldIcon from '@mui/icons-material/Shield'
import LogoutIcon from '@mui/icons-material/Logout'
import { useAuth } from '../context/AuthContext'
import { SIDEBAR_BG, SIDEBAR_FG } from '../theme'

const DRAWER_WIDTH = 244

const NAV = [
  { label: 'Dashboard', path: '/', icon: <DashboardIcon /> },
  { label: 'Accounts', path: '/accounts', icon: <PeopleIcon /> },
  { label: 'Transactions', path: '/transactions', icon: <ReceiptLongIcon /> },
  { label: 'Data Quality', path: '/data-quality', icon: <FactCheckIcon /> },
  { label: 'Rule Detection', path: '/rules', icon: <GavelIcon /> },
  { label: 'Graph Analysis', path: '/graph', icon: <HubIcon /> },
  { label: 'Features', path: '/features', icon: <TableChartIcon /> },
  { label: 'ML Scoring', path: '/ml', icon: <ModelTrainingIcon /> },
  { label: 'GNN', path: '/gnn', icon: <PsychologyIcon /> },
  { label: 'Fraud Alerts', path: '/alerts', icon: <WarningAmberIcon /> },
  { label: 'Fraud Rings', path: '/rings', icon: <GroupsIcon /> },
  { label: 'Investigations', path: '/cases', icon: <FolderSharedIcon /> },
  { label: 'Reports', path: '/reports', icon: <AssessmentIcon /> },
]

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            bgcolor: SIDEBAR_BG,
            color: SIDEBAR_FG,
            borderRight: 'none',
          },
        }}
      >
        <Toolbar sx={{ gap: 1.5, px: 2.5 }}>
          <ShieldIcon sx={{ color: '#818cf8' }} />
          <Box>
            <Typography sx={{ color: '#fff', fontWeight: 700, lineHeight: 1.1 }}>
              FraudGraph
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748b' }}>
              Detection Console
            </Typography>
          </Box>
        </Toolbar>
        <Divider sx={{ borderColor: '#1e293b' }} />
        <List sx={{ px: 1.5, pt: 1.5 }}>
          {NAV.map((item) => {
            const active = location.pathname === item.path
            return (
              <ListItemButton
                key={item.path}
                onClick={() => navigate(item.path)}
                sx={{
                  borderRadius: 2, mb: 0.5, color: active ? '#fff' : SIDEBAR_FG,
                  bgcolor: active ? 'rgba(129,140,248,0.16)' : 'transparent',
                  '&:hover': { bgcolor: 'rgba(148,163,184,0.10)' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 38, color: active ? '#818cf8' : '#64748b' }}>
                  {item.icon}
                </ListItemIcon>
                <ListItemText primaryTypographyProps={{ fontSize: 14, fontWeight: active ? 600 : 500 }}>
                  {item.label}
                </ListItemText>
              </ListItemButton>
            )
          })}
        </List>
      </Drawer>

      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
        <AppBar
          position="sticky"
          elevation={0}
          sx={{ bgcolor: 'background.paper', color: 'text.primary', borderBottom: '1px solid #e5e7eb' }}
        >
          <Toolbar sx={{ justifyContent: 'flex-end', gap: 2 }}>
            <Chip size="small" label="Admin" color="primary" variant="outlined" />
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 14 }}>
              {(user?.username || 'A')[0].toUpperCase()}
            </Avatar>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>{user?.username}</Typography>
            <Button size="small" startIcon={<LogoutIcon />} onClick={() => { logout(); navigate('/login') }}>
              Log out
            </Button>
          </Toolbar>
        </AppBar>
        <Box component="main" sx={{ p: 3, flexGrow: 1 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}
