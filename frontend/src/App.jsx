import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Accounts from './pages/Accounts'
import Transactions from './pages/Transactions'
import DataQuality from './pages/DataQuality'
import RuleDetection from './pages/RuleDetection'
import GraphAnalysis from './pages/GraphAnalysis'
import Features from './pages/Features'
import MLScoring from './pages/MLScoring'
import GNN from './pages/GNN'
import FraudRings from './pages/FraudRings'
import Alerts from './pages/Alerts'
import Cases from './pages/Cases'
import Reports from './pages/Reports'
import AccountDetail from './pages/AccountDetail'
import ModelAnalytics from './pages/ModelAnalytics'
import Notifications from './pages/Notifications'
import { NotificationsProvider } from './context/NotificationsContext'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <NotificationsProvider>
              <Layout />
            </NotificationsProvider>
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/accounts/:uid" element={<AccountDetail />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/data-quality" element={<DataQuality />} />
        <Route path="/rules" element={<RuleDetection />} />
        <Route path="/graph" element={<GraphAnalysis />} />
        <Route path="/features" element={<Features />} />
        <Route path="/ml" element={<MLScoring />} />
        <Route path="/gnn" element={<GNN />} />
        <Route path="/analytics" element={<ModelAnalytics />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/rings" element={<FraudRings />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/cases" element={<Cases />} />
        <Route path="/reports" element={<Reports />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
