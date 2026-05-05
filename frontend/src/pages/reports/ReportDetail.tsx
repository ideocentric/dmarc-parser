import { useState, Fragment } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Flag, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ResultBadge } from "@/components/shared/ResultBadge";
import { reportsApi, type Record as DmarcRecord } from "@/api/reports";
import { useClient } from "@/contexts/ClientContext";
import { useAuth } from "@/contexts/AuthContext";

// ---------------------------------------------------------------------------
// Expandable record detail panel
// ---------------------------------------------------------------------------

function RecordDetail({ rec }: { rec: DmarcRecord }) {
  const dkim = rec.auth_results.filter((a) => a.auth_type === "dkim");
  const spf  = rec.auth_results.filter((a) => a.auth_type === "spf");

  return (
    <div className="grid grid-cols-2 gap-x-8 gap-y-3 px-6 py-4 bg-muted/30 text-sm border-b">
      {/* Sender identity */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">Sender Identity</p>
        <div className="space-y-1">
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Header From</span>
            <span className="font-mono">{rec.header_from ?? "—"}</span>
          </div>
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Envelope From</span>
            <span className={`font-mono ${
              rec.envelope_from && rec.header_from && rec.envelope_from !== rec.header_from
                ? "text-amber-600"
                : ""
            }`}>
              {rec.envelope_from || "—"}
            </span>
          </div>
          {rec.envelope_to && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Envelope To</span>
              <span className="font-mono">{rec.envelope_to}</span>
            </div>
          )}
          {rec.whois_org && (
            <div className="flex gap-2 pt-1 border-t mt-1">
              <span className="w-28 shrink-0 text-muted-foreground">Organisation</span>
              <span>{rec.whois_org}</span>
            </div>
          )}
          {rec.whois_asn && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">ASN</span>
              <span className="font-mono">
                {rec.whois_asn}
                {rec.whois_as_name && <span className="ml-2 text-muted-foreground">{rec.whois_as_name}</span>}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Auth results detail */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">Authentication Detail</p>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="text-left font-medium pb-1 pr-3 w-10">Type</th>
              <th className="text-left font-medium pb-1 pr-3">Domain</th>
              <th className="text-left font-medium pb-1 pr-3">Selector</th>
              <th className="text-left font-medium pb-1">Result</th>
            </tr>
          </thead>
          <tbody>
            {[...dkim, ...spf].map((ar, i) => (
              <tr key={i}>
                <td className="pr-3 py-0.5 uppercase text-muted-foreground">{ar.auth_type}</td>
                <td className="pr-3 py-0.5 font-mono">{ar.domain}</td>
                <td className="pr-3 py-0.5 font-mono text-muted-foreground">{ar.selector ?? "—"}</td>
                <td className="py-0.5">
                  <ResultBadge result={ar.result} />
                </td>
              </tr>
            ))}
            {rec.auth_results.length === 0 && (
              <tr><td colSpan={4} className="text-muted-foreground italic">No auth results</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { currentSlug } = useClient();
  const slug = currentSlug ?? user?.client_slugs[0];
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const { data: report, isLoading } = useQuery({
    queryKey: ["report", slug, id],
    queryFn: () => reportsApi.get(slug!, Number(id)),
    enabled: !!slug && !!id,
  });

  const toggle = (recId: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(recId) ? next.delete(recId) : next.add(recId);
      return next;
    });

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }
  if (!report) return <p className="text-muted-foreground">Report not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-bold">{report.domain}</h1>
          <p className="text-sm text-muted-foreground">
            from {report.org_name} · {new Date(report.begin_date).toLocaleDateString()} – {new Date(report.end_date).toLocaleDateString()}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        {report.policy_p && <Badge variant="outline">policy: {report.policy_p}</Badge>}
        {report.policy_pct != null && <Badge variant="outline">pct: {report.policy_pct}%</Badge>}
        <Badge variant="outline">{report.record_count} records</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Records
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              — click a row to see sender detail and auth results
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="w-6 px-3 py-3" />
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Source IP</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Location</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Count</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Disposition</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">DKIM</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">SPF</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Header From</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Flags</th>
              </tr>
            </thead>
            <tbody>
              {report.records.map((rec) => {
                const isOpen = expanded.has(rec.id);
                return (
                  <Fragment key={rec.id}>
                    <tr
                      className="border-b hover:bg-muted/20 cursor-pointer"
                      onClick={() => toggle(rec.id)}
                    >
                      <td className="px-3 py-2 text-muted-foreground">
                        {isOpen
                          ? <ChevronDown className="h-3.5 w-3.5" />
                          : <ChevronRight className="h-3.5 w-3.5" />}
                      </td>
                      <td className="px-4 py-2">
                        <span className="font-mono text-xs">{rec.source_ip}</span>
                        {rec.whois_org && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {rec.whois_org}
                            {rec.whois_asn && <span className="ml-1 opacity-60">· {rec.whois_asn}</span>}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground text-xs">
                        {[rec.geo_city, rec.geo_subdivision, rec.geo_country].filter(Boolean).join(", ") || "—"}
                      </td>
                      <td className="px-4 py-2 text-right">{rec.count.toLocaleString()}</td>
                      <td className="px-4 py-2"><ResultBadge result={rec.disposition} /></td>
                      <td className="px-4 py-2"><ResultBadge result={rec.dkim_result} /></td>
                      <td className="px-4 py-2"><ResultBadge result={rec.spf_result} /></td>
                      <td className="px-4 py-2 text-muted-foreground text-xs">{rec.header_from ?? "—"}</td>
                      <td className="px-4 py-2 text-right">
                        {rec.flag_count > 0 && (
                          <span className="inline-flex items-center gap-1 text-orange-600">
                            <Flag className="h-3 w-3" />
                            {rec.flag_count}
                          </span>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={9} className="p-0">
                          <RecordDetail rec={rec} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}