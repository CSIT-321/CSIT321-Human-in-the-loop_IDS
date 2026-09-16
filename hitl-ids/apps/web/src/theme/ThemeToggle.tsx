import { useTheme } from "./ThemeContext";

function SunIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.5 14.2A8 8 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z" />
    </svg>
  );
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const currentLabel = theme === "dark" ? "Dark" : "Light";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Current theme: ${currentLabel}. Switch to ${next} theme.`}
      className="inline-flex h-8 items-center justify-center gap-1.5 rounded-sm border border-border bg-raised px-2 text-xs font-medium text-text transition-colors hover:border-border-strong hover:bg-surface"
    >
      {theme === "dark" ? <MoonIcon /> : <SunIcon />}
      <span className={compact ? "hidden sm:inline" : undefined}>{currentLabel}</span>
    </button>
  );
}
