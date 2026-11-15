import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';
import { AuthProvider } from './api/AuthContext';
import { GuardedRoute } from './components/GuardedRoute';
import { AdminCatalogPage } from './pages/AdminCatalogPage';
import { AdminKbPage } from './pages/AdminKbPage';
import { AdminSlotsPage } from './pages/AdminSlotsPage';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { SignupPage } from './pages/SignupPage';

function App(): ReactNode {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/signup" element={<GuardedRoute path="/signup"><SignupPage /></GuardedRoute>} />
          <Route path="/login" element={<GuardedRoute path="/login"><LoginPage /></GuardedRoute>} />
          <Route path="/onboarding" element={<GuardedRoute path="/onboarding"><OnboardingPage /></GuardedRoute>} />
          <Route path="/chat" element={<GuardedRoute path="/chat"><ChatPage /></GuardedRoute>} />
          <Route path="/chat/:sessionId" element={<GuardedRoute path="/chat"><ChatPage /></GuardedRoute>} />
          <Route path="/admin/catalog" element={<GuardedRoute path="/admin/catalog"><AdminCatalogPage /></GuardedRoute>} />
          <Route path="/admin/slots" element={<GuardedRoute path="/admin/slots"><AdminSlotsPage /></GuardedRoute>} />
          <Route path="/admin/kb" element={<GuardedRoute path="/admin/kb"><AdminKbPage /></GuardedRoute>} />
          <Route path="/" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
