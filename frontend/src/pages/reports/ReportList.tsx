import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FileText, ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Pagination } from "@/components/shared/Pagination";
import { reportsApi } from "@/api/reports";
import { useClient } from "@/contexts/ClientContext";
import { useAuth } from "@/contexts/AuthContext";

export function ReportList() {
  const { user } = useAuth();
  const { currentSlug } = useClient();
  const slug = currentSlug ?? user?.client_slugs[0];
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [domain, setDomain] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["reports", slug, page, domain],
    queryFn: () => reportsApi.list(slug!, { page, page_size: 25, domain: domain || undefined }),
    enabled: !!slug,
  });

  if (!slug) return <p className="text-muted-foreground">No client selected.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Reports</h1>
        <Input
          placeholder="Filter by domain…"
          value={domain}
          onChange={(e) => { setDomain(e.target.value); setPage(1); }}
          className="w-64"
        />
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
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Domain</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Reporter</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Period End</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Policy</th>
                  <th className="px-4 py-3 text-right font-medium text-muted-foreground">Records</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {data?.items.map((r) => (
                  <tr
                    key={r.id}
                    className="cursor-pointer border-b transition-colors hover:bg-muted/30"
                    onClick={() => navigate(`/reports/${r.id}`)}
                  >
                    <td className="px-4 py-3 font-medium">{r.domain}</td>
                    <td className="px-4 py-3 text-muted-foreground">{r.org_name}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(r.end_date).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      {r.policy_p && <Badge variant="outline">{r.policy_p}</Badge>}
                    </td>
                    <td className="px-4 py-3 text-right">{r.record_count}</td>
                    <td className="px-4 py-3">
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </td>
                  </tr>
                ))}
                {data?.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      <FileText className="mx-auto mb-2 h-8 w-8 opacity-30" />
                      No reports found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
          {data && (
            <Pagination
              page={page}
              pageSize={25}
              total={data.total}
              onPageChange={setPage}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}