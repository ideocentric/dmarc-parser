import { useState, useMemo } from "react";
import { ComposableMap, Geographies, Geography, ZoomableGroup, type Geography as Geo } from "react-simple-maps";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/api/analytics";
import { alpha2ToNumeric } from "@/lib/countryCodes";

const GEO_URL = "/countries-110m.json"; // bundled locally — avoids CDN supply-chain risk and IP leakage

const TIME_OPTIONS = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
  { label: "1 year", value: 365 },
];

interface Props {
  slug: string;
}

interface TooltipState {
  x: number;
  y: number;
  country: string;
  messages: number;
}

export function GeoDistributionMap({ slug }: Props) {
  const [days, setDays] = useState(30);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const { data = [], isLoading } = useQuery({
    queryKey: ["geo-distribution", slug, days],
    queryFn: () => analyticsApi.geoDistribution(slug, days),
  });

  // Build a lookup: numeric country code → message count
  const messagesByNumeric = useMemo(() => {
    const map: Record<string, number> = {};
    for (const row of data) {
      const numeric = alpha2ToNumeric[row.country.toUpperCase()];
      if (numeric) map[numeric] = row.messages;
    }
    return map;
  }, [data]);

  const maxMessages = useMemo(
    () => Math.max(1, ...data.map((r) => r.messages)),
    [data]
  );

  function fillForCount(count: number | undefined): string {
    if (!count) return "hsl(var(--muted))";
    const t = Math.pow(count / maxMessages, 0.4); // power scale for contrast
    // Interpolate between a light and saturated primary-ish blue
    const lightness = Math.round(70 - t * 50); // 70% → 20%
    return `hsl(221 83% ${lightness}%)`;
  }

  return (
    <div className="space-y-3">
      {/* Time window selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Last</span>
        {TIME_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setDays(opt.value)}
            className={[
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              days === opt.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
        {isLoading && (
          <div className="ml-2 h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        )}
      </div>

      {/* Map */}
      <div
        className="relative overflow-hidden rounded-md bg-muted/30"
        style={{ height: 340 }}
        onMouseLeave={() => setTooltip(null)}
      >
        <ComposableMap
          projectionConfig={{ scale: 140, center: [0, 20] }}
          style={{ width: "100%", height: "100%" }}
        >
          <ZoomableGroup zoom={1}>
            <Geographies geography={GEO_URL}>
              {({ geographies }: { geographies: Geo[] }) =>
                geographies.map((geo: Geo) => {
                  const id = String(geo.id);
                  const count = messagesByNumeric[id];
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      fill={fillForCount(count)}
                      stroke="hsl(var(--border))"
                      strokeWidth={0.4}
                      style={{
                        default: { outline: "none" },
                        hover: { outline: "none", opacity: 0.8 },
                        pressed: { outline: "none" },
                      }}
                      onMouseEnter={(e: React.MouseEvent<SVGPathElement>) => {
                        if (!count) return;
                        const rect = (e.currentTarget as SVGElement)
                          .closest("svg")!
                          .getBoundingClientRect();
                        setTooltip({
                          x: e.clientX - rect.left,
                          y: e.clientY - rect.top,
                          country: String(geo.properties.name ?? ""),
                          messages: count,
                        });
                      }}
                      onMouseMove={(e: React.MouseEvent<SVGPathElement>) => {
                        if (!count) return;
                        const rect = (e.currentTarget as SVGElement)
                          .closest("svg")!
                          .getBoundingClientRect();
                        setTooltip((prev) =>
                          prev
                            ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top }
                            : null
                        );
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  );
                })
              }
            </Geographies>
          </ZoomableGroup>
        </ComposableMap>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded bg-neutral-900 px-2 py-1 text-xs text-neutral-50 shadow"
            style={{ left: tooltip.x + 10, top: tooltip.y - 28 }}
          >
            <span className="font-medium">{tooltip.country}</span>
            <span className="ml-2 opacity-80">{tooltip.messages.toLocaleString()} msg</span>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-2 right-3 flex items-center gap-1.5 text-xs text-muted-foreground">
          <div
            className="h-2.5 w-12 rounded"
            style={{
              background: "linear-gradient(to right, hsl(221 83% 70%), hsl(221 83% 20%))",
            }}
          />
          <span>fewer → more</span>
        </div>

        {data.length === 0 && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            No geo data for this period.
          </div>
        )}
      </div>
    </div>
  );
}