interface BrandLogoProps {
  collapsed?: boolean;
  className?: string;
}

export function BrandLogo({ collapsed = false, className = "" }: BrandLogoProps) {
  return (
    <div
      className={`flex items-center gap-3 select-none ${className}`}
      title="ASCI — Adaptive Supply Chain Intelligence v2.0"
    >
      {/* Official Reusable Enterprise ASCI Mark */}
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-google-blue text-white shadow-sm transition-transform">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
        >
          {/* Interconnected triangular supply chain network topology */}
          <circle cx="12" cy="4" r="2" fill="currentColor" />
          <circle cx="5" cy="18" r="2" fill="currentColor" />
          <circle cx="19" cy="18" r="2" fill="currentColor" />
          <circle cx="12" cy="13" r="1.5" fill="currentColor" />
          <line x1="12" y1="6" x2="12" y2="11.5" />
          <line x1="6.5" y1="16.5" x2="10.8" y2="13.8" />
          <line x1="17.5" y1="16.5" x2="13.2" y2="13.8" />
          <line x1="7" y1="18" x2="17" y2="18" strokeDasharray="2 2" />
        </svg>
      </div>

      {!collapsed && (
        <div className="flex flex-col min-w-0 overflow-hidden leading-tight">
          <div className="flex items-center gap-1.5">
            <span className="text-base font-bold tracking-tight text-light-text-primary dark:text-dark-text-primary">
              ASCI
            </span>
            <span className="rounded border border-light-border bg-light-secondary px-1.5 py-0.5 text-[10px] font-semibold text-google-blue dark:border-dark-border dark:bg-dark-elevated">
              v2.0
            </span>
          </div>
          <span className="text-[11px] text-light-text-muted dark:text-dark-text-muted truncate">
            Supply Chain Intelligence
          </span>
        </div>
      )}
    </div>
  );
}

export default BrandLogo;

