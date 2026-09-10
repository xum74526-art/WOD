"use client";

import { Moon, Sun, Translate } from "@phosphor-icons/react";
import { useKaiTheme } from "@/components/theme-root";
import { useI18n } from "@/components/locale-root";

export function UiSettings({ compact = false }: { compact?: boolean }) {
  const { appearance, toggleAppearance } = useKaiTheme();
  const { locale, t, toggleLocale } = useI18n();
  const nextLabel = appearance === "dark" ? t("theme.toLight", "切换到浅色模式") : t("theme.toDark", "切换到深色模式");
  const languageLabel = locale === "zh-Hant"
    ? t("language.switchSimplified", "切换为简体中文")
    : locale === "zh-Hans"
      ? t("language.switchEnglish", "切换为英文")
      : t("language.switchTraditional", "切换为繁体中文");
  const languageMark = locale === "zh-Hant" ? "繁" : locale === "zh-Hans" ? "简" : "EN";
  return (
    <div className={`ui-settings-group${compact ? " ui-settings-group--compact" : ""}`}>
      <button className={`ui-settings${compact ? " ui-settings--compact" : ""}`} type="button" onClick={toggleLocale} aria-label={languageLabel} title={languageLabel}>
        <Translate size={17}/><span className="ui-language-code">{languageMark}</span>
        {!compact && <span>{locale === "zh-Hant" ? "繁體中文" : locale === "zh-Hans" ? "简体中文" : "English"}</span>}
      </button>
      <button className={`ui-settings${compact ? " ui-settings--compact" : ""}`} type="button" onClick={toggleAppearance} aria-label={nextLabel} title={nextLabel}>
        {appearance === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        {!compact && <span>{appearance === "dark" ? t("theme.light", "浅色模式") : t("theme.dark", "深色模式")}</span>}
      </button>
    </div>
  );
}
