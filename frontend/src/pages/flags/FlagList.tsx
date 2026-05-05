import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { CheckCircle, Circle, Flag } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { Pagination } from "@/components/shared/Pagination";
import { flagsApi } from "@/api/flags";
import { useClient } from "@/contexts/ClientContext";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

const FLAG_DESCRIPTIONS: Record<string, string> = {
  dkim_spf_both_fail:
    "Both DKIM signature verification and SPF sender authentication failed. Strong indicator of a spoofing attempt or a severely misconfigured sender.",
  spf_fail:
    "SPF check failed — the sending IP is not authorised by the domain's SPF record. Common in email forwarding scenarios; also seen with unauthorised senders.",
  dkim_fail:
    "DKIM signature failed — the message was not signed with the domain's private key, or the signature was invalid or tampered with.",
  policy_mismatch:
    "The message disposition was 'none' (delivered) even though the published DMARC policy is quarantine or reject. A local policy override is active on the receiving server.",
  forwarding_pattern:
    "SPF failed but DKIM passed — the classic signature of a forwarded email. Forwarding changes the envelope sender (breaking SPF alignment) while the original DKIM signature survives. Usually not harmful.",
  volume_spike:
    "This IP address sent significantly more messages than its historical average. May indicate a bulk campaign, compromised account, or anomalous sending behaviour.",
  geo_anomaly:
    "The source IP geolocates to a country flagged as high-risk in the platform configuration. Review whether this sender is expected to originate from that location.",
  new_sender_ip:
    "First time this IP address has been seen sending mail for this domain. Normal for new mail servers or providers; worth reviewing if unexpected.",
};

const SEVERITIES = ["", "critical", "high", "medium", "low", "info"];

export function FlagList() {
  const { user } = useAuth();
  const { currentSlug } = useClient();
  const slug = currentSlug ?? user?.client_slugs[0];
  const qc = useQueryClient();
  const location = useLocation();
  const nav = location.state as { severity?: string } | null;
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState(nav?.severity ?? "");
  const [unackOnly, setUnackOnly] = useState(true);

  const { data, isLoading } = useQuery({
    queryKey: ["flags", slug, page, severity, unackOnly],
    queryFn: () =>
      flagsApi.list(slug!, {
        page,
        page_size: 25,
        severity: severity || undefined,
        unacknowledged_only: unackOnly,
      }),
    enabled: !!slug,
  });

  const ackMutation = useMutation({
    mutationFn: ({ flagId, ack }: { flagId: number; ack: boolean }) =>
      ack ? flagsApi.acknowledge(slug!, flagId) : flagsApi.unacknowledge(slug!, flagId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["flags", slug] }),
  });

  if (!slug) return <p className="text-muted-foreground">No client selected.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Flags</h1>
        <div className="flex gap-2">
          {SEVERITIES.map((s) => (
            <button
              key={s}
              onClick={() => { setSeverity(s); setPage(1); }}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                severity === s
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {s || "All"}
            </button>
          ))}
          <button
            onClick={() => { setUnackOnly((v) => !v); setPage(1); }}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              unackOnly ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
            )}
          >
            Open only
          </button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="w-10 px-4 py-3" />
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Type</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Detail</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acknowledged by</th>
                  <th className="w-24 px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {data?.items.map((flag) => (
                  <tr key={flag.id} className={cn("border-b hover:bg-muted/20", flag.acknowledged_at && "opacity-50")}>
                    <td className="px-4 py-2">
                      <Flag className="h-4 w-4 text-muted-foreground" />
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {FLAG_DESCRIPTIONS[flag.flag_type] ? (
                        <Tooltip text={FLAG_DESCRIPTIONS[flag.flag_type]}>
                          <span className="underline decoration-dotted underline-offset-2">
                            {flag.flag_type}
                          </span>
                        </Tooltip>
                      ) : (
                        flag.flag_type
                      )}
                    </td>
                    <td className="px-4 py-2"><SeverityBadge severity={flag.severity} /></td>
                    <td className="px-4 py-2 font-mono text-xs text-muted-foreground max-w-xs truncate">
                      {flag.detail ? JSON.stringify(flag.detail) : "—"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {new Date(flag.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {flag.acknowledged_by ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => ackMutation.mutate({ flagId: flag.id, ack: !flag.acknowledged_at })}
                        disabled={ackMutation.isPending}
                      >
                        {flag.acknowledged_at ? (
                          <><Circle className="mr-1 h-3 w-3" /> Reopen</>
                        ) : (
                          <><CheckCircle className="mr-1 h-3 w-3" /> Acknowledge</>
                        )}
                      </Button>
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      <Flag className="mx-auto mb-2 h-8 w-8 opacity-30" />
                      No flags match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
          {data && (
            <Pagination page={page} pageSize={25} total={data.total} onPageChange={setPage} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}