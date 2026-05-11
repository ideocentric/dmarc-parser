import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { authApi, type UserMe } from "@/api/auth";

interface AuthState {
  user: UserMe | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export type LoginResult =
  | { status: "ok" }
  | { status: "mfa_required"; mfa_token: string };

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfa_token: string, code: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserMe | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
    } catch {
      setUser(null);
      localStorage.removeItem("access_token");
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      refreshUser().finally(() => setIsLoading(false));
    } else {
      authApi.refresh()
        .then((tokens) => {
          localStorage.setItem("access_token", tokens.access_token);
          return refreshUser();
        })
        .catch(() => {})
        .finally(() => setIsLoading(false));
    }
  }, [refreshUser]);

  // Clear auth state when the axios interceptor detects a session expiry on
  // a non-auth API call. React Router then navigates to /login naturally —
  // no hard page reload.
  useEffect(() => {
    const handleExpired = () => {
      setUser(null);
      localStorage.removeItem("access_token");
    };
    window.addEventListener("auth:session-expired", handleExpired);
    return () => window.removeEventListener("auth:session-expired", handleExpired);
  }, []);

  const login = async (email: string, password: string): Promise<LoginResult> => {
    const result = await authApi.login(email, password);
    if (result.mfa_required && result.mfa_token) {
      return { status: "mfa_required", mfa_token: result.mfa_token };
    }
    if (result.access_token) {
      localStorage.setItem("access_token", result.access_token);
    }
    await refreshUser();
    return { status: "ok" };
  };

  const verifyMfa = async (mfa_token: string, code: string) => {
    const tokens = await authApi.mfaVerify(mfa_token, code);
    localStorage.setItem("access_token", tokens.access_token);
    await refreshUser();
  };

  const logout = () => {
    authApi.logout().catch(() => {});
    localStorage.removeItem("access_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: !!user, login, verifyMfa, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}