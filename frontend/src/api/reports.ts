import api from "./client";

export interface AuthResult {
  id: number;
  auth_type: string;
  domain: string;
  result: string;
  selector: string | null;
}

export interface Record {
  id: number;
  source_ip: string;
  count: number;
  disposition: string;
  dkim_result: string;
  spf_result: string;
  header_from: string | null;
  envelope_from: string | null;
  envelope_to: string | null;
  geo_country: string | null;
  geo_city: string | null;
  geo_subdivision: string | null;
  whois_org: string | null;
  whois_asn: string | null;
  whois_as_name: string | null;
  auth_results: AuthResult[];
  flag_count: number;
}

export interface Report {
  id: number;
  domain: string;
  org_name: string;
  org_email: string | null;
  report_id: string;
  begin_date: string;
  end_date: string;
  policy_p: string | null;
  policy_pct: number | null;
  source_filename: string;
  ingested_at: string;
  record_count: number;
}

export interface ReportDetail extends Report {
  records: Record[];
}

export interface Paginated<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export const reportsApi = {
  list: (slug: string, params?: { domain?: string; page?: number; page_size?: number }) =>
    api.get<Paginated<Report>>(`/clients/${slug}/reports`, { params }).then((r) => r.data),

  get: (slug: string, id: number) =>
    api.get<ReportDetail>(`/clients/${slug}/reports/${id}`).then((r) => r.data),

  listRecords: (
    slug: string,
    params?: {
      source_ip?: string;
      disposition?: string;
      dkim_result?: string;
      spf_result?: string;
      has_flags?: boolean;
      page?: number;
      page_size?: number;
    }
  ) => api.get<Paginated<Record>>(`/clients/${slug}/records`, { params }).then((r) => r.data),
};