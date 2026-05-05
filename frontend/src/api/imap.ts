import api from "./client";

export interface ImapConfig {
  id: number;
  client_id: number;
  auth_type: "imap" | "office365";
  host: string;
  port: number;
  username: string;
  use_ssl: boolean;
  inbox_folder: string;
  processed_folder: string | null;
  poll_interval_minutes: number;
  is_active: boolean;
  last_polled_at: string | null;
  last_poll_status: string | null;
  last_poll_message: string | null;
  oauth2_tenant_id: string | null;
  oauth2_client_id: string | null;
  created_at: string;
}

export interface PollResult {
  status: string;
  messages_scanned: number;
  reports_ingested: number;
  message: string;
}

type ImapCreate =
  | {
      auth_type: "imap";
      username: string;
      host: string;
      port: number;
      password: string;
      use_ssl: boolean;
      inbox_folder: string;
      processed_folder: string | null;
      poll_interval_minutes: number;
    }
  | {
      auth_type: "office365";
      username: string;
      oauth2_tenant_id: string;
      oauth2_client_id: string;
      oauth2_client_secret: string;
      inbox_folder: string;
      processed_folder: string | null;
      poll_interval_minutes: number;
    };

export const imapApi = {
  get: (slug: string) =>
    api.get<ImapConfig>(`/clients/${slug}/imap`).then((r) => r.data),

  create: (slug: string, data: ImapCreate) =>
    api.post<ImapConfig>(`/clients/${slug}/imap`, data).then((r) => r.data),

  update: (slug: string, data: Partial<{
    username: string;
    host: string; port: number; password: string; use_ssl: boolean;
    inbox_folder: string; processed_folder: string | null;
    poll_interval_minutes: number; is_active: boolean;
    oauth2_tenant_id: string; oauth2_client_id: string; oauth2_client_secret: string;
  }>) => api.patch<ImapConfig>(`/clients/${slug}/imap`, data).then((r) => r.data),

  delete: (slug: string) => api.delete(`/clients/${slug}/imap`),

  test: (slug: string) =>
    api.post<PollResult>(`/clients/${slug}/imap/test`).then((r) => r.data),

  poll: (slug: string) =>
    api.post<PollResult>(`/clients/${slug}/imap/poll`).then((r) => r.data),
};