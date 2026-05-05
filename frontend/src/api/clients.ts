import api from "./client";

export interface ClientPurgeResponse {
  slug: string;
  purged_at: string;
  deleted: Record<string, number>;
  deactivated_users: string[];
  filesystem_removed: string[];
}

export interface Client {
  id: number;
  slug: string;
  name: string;
  is_active: boolean;
  mfa_required_admins: boolean;
  mfa_required_viewers: boolean;
  created_at: string;
}

export interface Domain {
  id: number;
  client_id: number;
  domain: string;
  is_active: boolean;
  created_at: string;
}

export const clientsApi = {
  list: () => api.get<Client[]>("/clients").then((r) => r.data),

  create: (slug: string, name: string) =>
    api.post<Client>("/clients", { slug, name }).then((r) => r.data),

  update: (slug: string, data: Partial<{ name: string; is_active: boolean }>) =>
    api.patch<Client>(`/clients/${slug}`, data).then((r) => r.data),

  listDomains: (slug: string) =>
    api.get<Domain[]>(`/clients/${slug}/domains`).then((r) => r.data),

  addDomain: (slug: string, domain: string) =>
    api.post<Domain>(`/clients/${slug}/domains`, { domain }).then((r) => r.data),

  removeDomain: (slug: string, domainId: number) =>
    api.delete(`/clients/${slug}/domains/${domainId}`),

  updateMfaPolicy: (slug: string, data: { mfa_required_admins?: boolean; mfa_required_viewers?: boolean }) =>
    api.patch<Client>(`/clients/${slug}/mfa-policy`, data).then((r) => r.data),

  exportClient: (slug: string): Promise<Blob> =>
    api.post(`/clients/${slug}/export`, null, { responseType: "blob" }).then((r) => r.data),

  purgeClient: (slug: string, confirmSlug: string) =>
    api.delete<ClientPurgeResponse>(`/clients/${slug}`, { data: { confirm_slug: confirmSlug } }).then((r) => r.data),
};