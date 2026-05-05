import api from "./client";
import type { Paginated } from "./reports";

export interface Flag {
  id: number;
  record_id: number;
  flag_type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  detail: Record<string, unknown> | null;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export const flagsApi = {
  list: (
    slug: string,
    params?: {
      severity?: string;
      flag_type?: string;
      unacknowledged_only?: boolean;
      page?: number;
      page_size?: number;
    }
  ) => api.get<Paginated<Flag>>(`/clients/${slug}/flags`, { params }).then((r) => r.data),

  acknowledge: (slug: string, flagId: number) =>
    api.post<Flag>(`/clients/${slug}/flags/${flagId}/acknowledge`, {}).then((r) => r.data),

  unacknowledge: (slug: string, flagId: number) =>
    api.post<Flag>(`/clients/${slug}/flags/${flagId}/unacknowledge`, {}).then((r) => r.data),
};