import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { AppLayout } from "@/components/layout/AppLayout";
import { Login } from "@/pages/Login";
import { ChangePassword } from "@/pages/ChangePassword";
import { MfaSetup } from "@/pages/MfaSetup";
import { Dashboard } from "@/pages/Dashboard";
import { ReportList } from "@/pages/reports/ReportList";
import { ReportDetail } from "@/pages/reports/ReportDetail";
import { FlagList } from "@/pages/flags/FlagList";
import { Analytics } from "@/pages/Analytics";
import { ClientList } from "@/pages/clients/ClientList";
import { UserList } from "@/pages/users/UserList";
import { canAccessClients, canAccessUsers } from "@/lib/permissions";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

function RequireAccess({ allowed, children }: { allowed: boolean; children: ReactNode }) {
  return allowed ? <>{children}</> : <Navigate to="/dashboard" replace />;
}

// Rendered inside AuthProvider so useAuth() is available
function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/change-password" element={<ChangePassword />} />
        <Route path="/mfa-setup" element={<MfaSetup />} />
        <Route path="/reports" element={<ReportList />} />
        <Route path="/reports/:id" element={<ReportDetail />} />
        <Route path="/flags" element={<FlagList />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route
          path="/clients"
          element={
            <RequireAccess allowed={canAccessClients(user)}>
              <ClientList />
            </RequireAccess>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAccess allowed={canAccessUsers(user)}>
              <UserList />
            </RequireAccess>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}