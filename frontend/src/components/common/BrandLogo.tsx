interface BrandLogoProps {
  collapsed?: boolean;
  className?: string;
}

export function BrandLogo({ collapsed = false, className = "" }: BrandLogoProps) {
  return (
    <div
      className={`flex items-center gap-2.5 select-none min-w-0 ${className}`}
      title="ASCI — Adaptive Supply Chain Intelligence v2.0"
    >
      {/* Official Enterprise ASCI Mark — Precise Network Topology */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-google-blue text-white shadow-sm ring-1 ring-blue-600/30">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4.5 w-4.5"
        >
          {/* Triangular multimodal supply chain network topology */}
          <circle cx="12" cy="4" r="2.2" fill="currentColor" />
          <circle cx="5" cy="19" r="2.2" fill="currentColor" />
          <circle cx="19" cy="19" r="2.2" fill="currentColor" />
          <circle cx="12" cy="13" r="1.5" fill="currentColor" />
          <line x1="12" y1="6.2" x2="12" y2="11.5" />
          <line x1="6.8" y1="17.2" x2="10.8" y2="14" />
          <line x1="17.2" y1="17.2" x2="13.2" y2="14" />
          <line x1="7.2" y1="19" x2="16.8" y2="19" strokeDasharray="2 2" />
        </svg>
      </div>

      {!collapsed && (
        <div className="flex flex-col min-w-0 flex-1 overflow-hidden leading-tight">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm font-bold tracking-tight text-light-text-primary dark:text-dark-text-primary truncate">
              ASCI
            </span>
            <span className="shrink-0 rounded border border-light-border bg-light-secondary px-1.5 py-0.2 text-[9px] font-bold text-google-blue dark:border-dark-border dark:bg-dark-elevated">
              v2.0
            </span>
          </div>
          <span className="text-[10px] text-light-text-muted dark:text-dark-text-muted truncate mt-0.5">
            Supply Chain Intelligence
          </span>
        </div>
      )}
    </div>
  );
}

export default BrandLogo;

