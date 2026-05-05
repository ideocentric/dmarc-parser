import { useQuery } from "@tanstack/react-query";
import { FileText, Flag, AlertTriangle, Activity } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/shared/SeverityBadge";
import { GeoDistributionMap } from "@/components/shared/GeoDistributionMap";
import { analyticsApi } from "@/api/analytics";
import { flagsApi } from "@/api/flags";
import { useClient } from "@/contexts/ClientContext";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Clickable stat card
// ---------------------------------------------------------------------------
function StatCard({
  icon: Icon, label, value, sub, to, state,
}: {
  icon: typeof FileText;
  label: string;
  value: string | number;
  sub?: string;
  to: string;
  state?: Record<string, unknown>;
}) {
  return (
    <Link
      to={to}
      state={state}
      className="block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="transition-shadow hover:shadow-md cursor-pointer h-full">
        <CardContent className="flex items-center gap-4 pt-6">
          <div className="rounded-lg bg-primary/10 p-3">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="text-2xl font-bold">{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export function Dashboard() {
  const { user } = useAuth();
  const { currentSlug } = useClient();
  const slug = currentSlug ?? user?.client_slugs[0];
  const navigate = useNavigate();

  const { data: analytics } = useQuery({
    queryKey: ["analytics", slug],
    queryFn: () => (slug ? analyticsApi.client(slug) : null),
    enabled: !!slug,
  });

  const { data: recentFlags } = useQuery({
    queryKey: ["flags", slug, "recent"],
    queryFn: () => (slug ? flagsApi.list(slug, { unacknowledged_only: true, page_size: 5 }) : null),
    enabled: !!slug,
  });

  if (!slug) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        {user?.role === "super_admin"
          ? "Select a client from the header to view its dashboard."
          : "No client assigned to your account yet."}
      </div>
    );
  }

  const bySev = analytics?.flags_by_severity ?? {};
  const criticalHigh = (bySev["critical"] ?? 0) + (bySev["high"] ?? 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Overview for {slug}</p>
      </div>

      {/* ── Stat cards ──────────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={FileText}
          label="Total Reports"
          value={analytics?.total_reports ?? "—"}
          to="/reports"
        />
        <StatCard
          icon={Activity}
          label="Total Messages"
          value={(analytics?.total_messages ?? 0).toLocaleString()}
          to="/reports"
        />
        <StatCard
          icon={Flag}
          label="Open Flags"
          value={analytics?.open_flags ?? "—"}
          to="/flags"
        />
        <StatCard
          icon={AlertTriangle}
          label="Critical / High"
          value={criticalHigh}
          sub="unacknowledged"
          to="/flags"
          state={{ severity: "critical" }}
        />
      </div>

      {/* ── Geo distribution map ────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Message Volume by Country</CardTitle>
        </CardHeader>
        <CardContent>
          <GeoDistributionMap slug={slug} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── Flags by severity ─────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Open Flags by Severity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {["critical", "high", "medium", "low", "info"].map((sev) => {
              const count = bySev[sev] ?? 0;
              return (
                <button
                  key={sev}
                  disabled={count === 0}
                  onClick={() => navigate("/flags", { state: { severity: sev } })}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md px-2 py-1.5 transition-colors",
                    count > 0
                      ? "hover:bg-muted cursor-pointer"
                      : "cursor-default opacity-50"
                  )}
                >
                  <SeverityBadge severity={sev} />
                  <span className="font-medium">{count}</span>
                </button>
              );
            })}
          </CardContent>
        </Card>

        {/* ── Recent unacknowledged flags ────────────────────────────────── */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recent Flags</CardTitle>
            <Link to="/flags" className="text-xs text-primary hover:underline">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {recentFlags?.items.length === 0 && (
              <p className="text-sm text-muted-foreground">No open flags.</p>
            )}
            <ul className="space-y-1">
              {recentFlags?.items.map((flag) => (
                <li key={flag.id}>
                  <button
                    onClick={() =>
                      navigate("/flags", { state: { severity: flag.severity } })
                    }
                    className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-muted transition-colors cursor-pointer"
                  >
                    <span className="font-mono text-xs text-muted-foreground">
                      {flag.flag_type}
                    </span>
                    <SeverityBadge severity={flag.severity} />
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}