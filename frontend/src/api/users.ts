import api from "./client";

export interface ClientRoleEntry {
  slug: string;
  role: "admin" | "viewer";
}

export interface User {
  id: number;
  email: string;
  role: "super_admin" | "user";
  is_active: boolean;
  must_change_password: boolean;
  mfa_enabled: boolean;
  created_at: string;
  client_slugs: string[];
  client_roles: ClientRoleEntry[];
}

export const usersApi = {
  list: () => api.get<User[]>("/users").then((r) => r.data),

  create: (data: {
    email: string;
    password: string;
    role: string;
    client_roles: ClientRoleEntry[];
  }) => api.post<User>("/users", data).then((r) => r.data),

  update: (
    id: number,
    data: Partial<{
      email: string;
      role: string;
      is_active: boolean;
      client_roles: ClientRoleEntry[];
    }>
  ) => api.patch<User>(`/users/${id}`, data).then((r) => r.data),

  resetPassword: (id: number, data: { new_password: string; temporary: boolean }) =>
    api.post(`/users/${id}/reset-password`, data),

  changePassword: (id: number, data: { old_password: string; new_password: string }) =>
    api.post(`/users/${id}/change-password`, data),

  deactivate: (id: number) => api.delete(`/users/${id}`),

  resetMfa: (id: number) => api.post(`/users/${id}/reset-mfa`),
};