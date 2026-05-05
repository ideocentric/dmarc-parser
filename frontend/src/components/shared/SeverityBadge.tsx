import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const severityConfig: Record<string, { label: string; className: string }> = {
  critical: { label: "Critical", className: "bg-red-600 text-white border-red-600" },
  high:     { label: "High",     className: "bg-orange-500 text-white border-orange-500" },
  medium:   { label: "Medium",   className: "bg-yellow-500 text-white border-yellow-500" },
  low:      { label: "Low",      className: "bg-blue-500 text-white border-blue-500" },
  info:     { label: "Info",     className: "bg-gray-400 text-white border-gray-400" },
};

export function SeverityBadge({ severity }: { severity: string }) {
  const cfg = severityConfig[severity] ?? { label: severity, className: "" };
  return <Badge className={cn(cfg.className)}>{cfg.label}</Badge>;
}