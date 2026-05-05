import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { analyticsApi } from "@/api/analytics";
import { useClient } from "@/contexts/ClientContext";
import { useAuth } from "@/contexts/AuthContext";

export function Analytics() {
  const { user } = useAuth();
  const { currentSlug } = useClient();
  const slug = currentSlug ?? user?.client_slugs[0];

  const { data, isLoading } = useQuery({
    queryKey: ["analytics", slug],
    queryFn: () => (slug ? analyticsApi.client(slug) : null),
    enabled: !!slug,
  });

  if (!slug) return <p className="text-muted-foreground">No client selected.</p>;

  if (isLoading) {
    return <div className="flex h-32 items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>;
  }

  const volumeData = [...(data?.daily_volume ?? [])].reverse();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Analytics — {slug}</h1>

      {/* Daily message volume */}
      <Card>
        <CardHeader><CardTitle className="text-base">Daily Message Volume (last 30 days)</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={volumeData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="total_messages" name="Messages" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Top sending IPs */}
      <Card>
        <CardHeader><CardTitle className="text-base">Top Sending IPs</CardTitle></CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP Address</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organisation</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Location</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Messages</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Reports</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Failures</th>
              </tr>
            </thead>
            <tbody>
              {data?.top_ips.map((ip) => {
                const parts = [ip.geo_city, ip.geo_subdivision, ip.geo_country].filter(Boolean);
                const location = parts.length > 0 ? parts.join(", ") : "—";
                const org = ip.whois_org
                  ? ip.whois_asn ? `${ip.whois_org} (${ip.whois_asn})` : ip.whois_org
                  : "—";
                return (
                  <tr key={ip.source_ip} className="border-b hover:bg-muted/20">
                    <td className="px-4 py-2 font-mono text-xs">{ip.source_ip}</td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">{org}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">{location}</td>
                    <td className="px-4 py-2 text-right">{ip.total_messages.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right">{ip.report_count}</td>
                    <td className="px-4 py-2 text-right text-red-600">{ip.failure_count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}