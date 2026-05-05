import { cn } from "@/lib/utils";

const resultColors: Record<string, string> = {
  pass:       "text-green-700 bg-green-50 border border-green-200",
  fail:       "text-red-700 bg-red-50 border border-red-200",
  softfail:   "text-orange-700 bg-orange-50 border border-orange-200",
  neutral:    "text-gray-600 bg-gray-50 border border-gray-200",
  none:       "text-gray-500 bg-gray-50 border border-gray-200",
  permerror:  "text-red-800 bg-red-100 border border-red-300",
  temperror:  "text-yellow-800 bg-yellow-100 border border-yellow-300",
  unknown:    "text-gray-500 bg-gray-50 border border-gray-200",
};

export function ResultBadge({ result }: { result: string }) {
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-xs font-medium", resultColors[result] ?? resultColors.unknown)}>
      {result}
    </span>
  );
}