import api from "./client";

export interface LoginResponse {
  mfa_required: boolean;
  mfa_token?: string;
  access_token?: string;
  token_type: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  // refresh_token is now an HttpOnly cookie set by the server
}

export interface MfaSetupResponse {
  otpauth_uri: string;
  qr_data_uri: string;
}

export interface ClientRoleEntry {
  slug: string;
  role: "admin" | "viewer";
}

export interface UserMe {
  id: number;
  email: string;
  role: "super_admin" | "user";
  is_active: boolean;
  must_change_password: boolean;
  has_password: boolean;
  mfa_enabled: boolean;
  mfa_setup_required: boolean;  // true when MFA is required but not yet enrolled
  mfa_required: boolean;        // true when the platform enforces MFA for all users
  created_at: string;
  client_slugs: string[];
  client_roles: ClientRoleEntry[];
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/auth/login", { email, password }).then((r) => r.data),

  mfaVerify: (mfa_token: string, code: string) =>
    api.post<TokenResponse>("/auth/mfa/verify", { mfa_token, code }).then((r) => r.data),

  mfaSetup: () =>
    api.post<MfaSetupResponse>("/auth/mfa/setup").then((r) => r.data),

  mfaConfirm: (code: string) =>
    api.post<TokenResponse>("/auth/mfa/confirm", { code }).then((r) => r.data),

  mfaDisable: (code: string) =>
    api.post("/auth/mfa/disable", { code }),

  refresh: () =>
    api.post<TokenResponse>("/auth/refresh").then((r) => r.data),

  logout: () => api.post("/auth/logout"),

  me: () => api.get<UserMe>("/auth/me").then((r) => r.data),

  azureLoginUrl: () =>
    api.get<{ auth_url: string; state: string }>("/auth/azure/login").then((r) => r.data),

  azureCallback: (code: string, state: string) =>
    api.post<TokenResponse>("/auth/azure/callback", { code, state }).then((r) => r.data),
};