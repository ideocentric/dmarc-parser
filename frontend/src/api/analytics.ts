import api from "./client";

export interface IPSummary {
  source_ip: string;
  geo_country: string | null;
  geo_city: string | null;
  geo_subdivision: string | null;
  whois_org: string | null;
  whois_asn: string | null;
  total_messages: number;
  report_count: number;
  failure_count: number;
}

export interface DailyVolume {
  date: string;
  total_messages: number;
  pass_count: number;
  fail_count: number;
}

export interface ClientAnalytics {
  client_slug: string;
  total_reports: number;
  total_records: number;
  total_messages: number;
  open_flags: number;
  flags_by_severity: Record<string, number>;
  top_ips: IPSummary[];
  daily_volume: DailyVolume[];
}

export interface CrossClientSummary {
  total_clients: number;
  total_reports: number;
  total_open_flags: number;
  clients: ClientAnalytics[];
}

export interface GeoDistributionEntry {
  country: string;
  messages: number;
}

export const analyticsApi = {
  client: (slug: string) =>
    api.get<ClientAnalytics>(`/clients/${slug}/analytics`).then((r) => r.data),

  crossClient: () =>
    api.get<CrossClientSummary>("/analytics").then((r) => r.data),

  geoDistribution: (slug: string, days = 30) =>
    api
      .get<GeoDistributionEntry[]>(`/clients/${slug}/analytics/geo-distribution`, { params: { days } })
      .then((r) => r.data),
};