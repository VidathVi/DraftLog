import { cn } from "@/lib/utils";

// DraftLog lockup: mark + wordmark share one coordinate system so the gap
// is exact. Canonical geometry lives in /branding. The page and "Draft"
// inherit currentColor (theme-aware); the accent lines and "Log" carry Teal.
export function Logomark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label="DraftLog logomark"
    >
      <path d="M10 6 H42 L54 18 V58 H10 Z" fill="currentColor" />
      <path d="M42 6 L54 18 H42 Z" fill="#0EA5E9" opacity="0.5" />
      <line x1="18" y1="28" x2="48" y2="28" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="18" y1="36" x2="44" y2="36" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
      <line x1="18" y1="44" x2="38" y2="44" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 340 64"
      overflow="visible"
      className={cn("h-8 w-auto", className)}
      role="img"
      aria-label="DraftLog"
    >
      <g transform="translate(-12 -3.5)">
        <path d="M10 6 H42 L54 18 V58 H10 Z" fill="currentColor" />
        <path d="M42 6 L54 18 H42 Z" fill="#0EA5E9" opacity="0.5" />
        <line x1="18" y1="28" x2="48" y2="28" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="18" y1="36" x2="44" y2="36" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="18" y1="44" x2="38" y2="44" stroke="#0EA5E9" strokeWidth="2.5" strokeLinecap="round" />
      </g>
      <text
        x="57"
        y="46"
        fontFamily="Inter, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif"
        fontSize="48"
        fontWeight="600"
        letterSpacing="-0.8"
        fill="currentColor"
      >
        Draft
        <tspan fill="#0EA5E9">Log</tspan>
      </text>
    </svg>
  );
}
