import { Moon, Sun } from "lucide-react";
import { useTheme } from "../../contexts/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme, isDark } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="relative flex h-8 w-8 items-center justify-center rounded-md border border-light-border bg-light-surface text-light-text-secondary transition hover:bg-light-hover hover:text-light-text-primary dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary dark:hover:bg-dark-elevated dark:hover:text-dark-text-primary shadow-subtle"
      title={`Switch to ${isDark ? "Light" : "Dark"} theme`}
      aria-label="Toggle theme"
    >
      {isDark ? (
        <Sun className="h-4 w-4 text-amber-400 transition-transform duration-300 rotate-0 hover:rotate-45" />
      ) : (
        <Moon className="h-4 w-4 text-slate-700 transition-transform duration-300 -rotate-12 hover:rotate-0" />
      )}
    </button>
  );
}

