"use client";

import { Moon, Sun } from "@phosphor-icons/react";
import { useKaiTheme } from "@/components/theme-root";

export function UiSettings({ compact = false }: { compact?: boolean }) {
  const { appearance, toggleAppearance } = useKaiTheme();
  const nextLabel = appearance === "dark" ? "切换到浅色模式" : "切换到深色模式";
  return (
    <button className={`ui-settings${compact ? " ui-settings--compact" : ""}`} type="button" onClick={toggleAppearance} aria-label={nextLabel} title={nextLabel}>
      {appearance === "dark" ? <Sun size={17} /> : <Moon size={17} />}
      {!compact && <span>{appearance === "dark" ? "浅色模式" : "深色模式"}</span>}
    </button>
  );
}
