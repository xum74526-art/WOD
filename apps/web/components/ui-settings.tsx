"use client";

import { CaretDown, Moon, Sun, Translate } from "@phosphor-icons/react";
import { useKaiTheme } from "@/components/theme-root";
import { useI18n } from "@/components/locale-root";
import type { KaiLocale } from "@/lib/language";

const LANGUAGE_OPTIONS: Array<{ value: KaiLocale; label: string; mark: string }> = [
  { value: "zh-Hant", label: "繁體中文", mark: "繁" },
  { value: "zh-Hans", label: "简体中文", mark: "简" },
  { value: "en", label: "English", mark: "EN" },
];

export function UiSettings({ compact = false }: { compact?: boolean }) {
  const { appearance, toggleAppearance } = useKaiTheme();
  const { locale, setLocale, t } = useI18n();
  const nextLabel = appearance === "dark" ? t("theme.toLight", "切换到浅色模式") : t("theme.toDark", "切换到深色模式");
  const selectedLanguage = LANGUAGE_OPTIONS.find((option) => option.value === locale) ?? LANGUAGE_OPTIONS[0];
  const languageLabel = t("language.choose", "选择语言");
  return (
    <div className={`ui-settings-group${compact ? " ui-settings-group--compact" : ""}`}>
      <label className={`ui-settings ui-settings--language${compact ? " ui-settings--compact" : ""}`} title={languageLabel}>
        <Translate size={17} aria-hidden="true" />
        <span className="ui-language-code">{selectedLanguage.mark}</span>
        {!compact && <span>{selectedLanguage.label}</span>}
        <CaretDown className="ui-language-caret" size={13} aria-hidden="true" />
        <select
          className="ui-language-select"
          value={locale}
          onChange={(event) => setLocale(event.target.value as KaiLocale)}
          aria-label={languageLabel}
          data-i18n-skip
        >
          {LANGUAGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <button className={`ui-settings${compact ? " ui-settings--compact" : ""}`} type="button" onClick={toggleAppearance} aria-label={nextLabel} title={nextLabel}>
        {appearance === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        {!compact && <span>{appearance === "dark" ? t("theme.light", "浅色模式") : t("theme.dark", "深色模式")}</span>}
      </button>
    </div>
  );
}
