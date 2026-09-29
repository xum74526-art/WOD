"use client";

import { CaretDown, GlobeSimple, Moon, Sun } from "@phosphor-icons/react";
import { DropdownMenu } from "@radix-ui/themes";
import { useState } from "react";
import { useKaiTheme } from "@/components/theme-root";
import { useI18n } from "@/components/locale-root";
import type { KaiLocale } from "@/lib/language";
import type { DisplayCurrencyCode } from "@/lib/display-currency";

const LANGUAGE_OPTIONS: Array<{ value: KaiLocale; label: string; code: string }> = [
  { value: "zh-Hant", label: "繁體中文", code: "zh-TW" },
  { value: "zh-Hans", label: "简体中文", code: "zh-CN" },
  { value: "en", label: "English", code: "en-US" },
];

const CURRENCY_OPTIONS: Array<{ value: DisplayCurrencyCode; label: string; symbol: string }> = [
  { value: "CNY", label: "人民币", symbol: "¥" },
  { value: "HKD", label: "港币", symbol: "HK$" },
  { value: "USD", label: "美元", symbol: "US$" },
];

export function UiSettings({ compact = false }: { compact?: boolean }) {
  const { appearance, toggleAppearance } = useKaiTheme();
  const { locale, setLocale, displayCurrency, setDisplayCurrency, t } = useI18n();
  const [languageOpen, setLanguageOpen] = useState(false);
  const nextLabel = appearance === "dark" ? t("theme.toLight", "切换到浅色模式") : t("theme.toDark", "切换到深色模式");
  const selectedLanguage = LANGUAGE_OPTIONS.find((option) => option.value === locale) ?? LANGUAGE_OPTIONS[0];
  const languageLabel = t("language.choose", "选择语言");
  const currentLanguageLabel = t("language.control", "选择语言，当前语言：{language}", { language: selectedLanguage.label });

  function selectLanguage(value: string) {
    setLocale(value as KaiLocale);
    setLanguageOpen(false);
  }

  return (
    <div className={`ui-settings-group${compact ? " ui-settings-group--compact" : ""}`}>
      <DropdownMenu.Root open={languageOpen} onOpenChange={setLanguageOpen}>
        <DropdownMenu.Trigger>
          <button
            className="ui-settings ui-settings--language"
            type="button"
            aria-label={currentLanguageLabel}
            title={languageLabel}
          >
            <GlobeSimple size={18} aria-hidden="true" />
            <span className="ui-language-current">
              <span className="ui-language-name">{selectedLanguage.label}</span>
              <span className="ui-language-code">{selectedLanguage.code} · {displayCurrency}</span>
            </span>
            <CaretDown className={`ui-language-caret${languageOpen ? " is-open" : ""}`} size={13} aria-hidden="true" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content
          align="end"
          sideOffset={10}
          collisionPadding={15}
          className="ui-language-popover"
          aria-label={languageLabel}
          data-i18n-skip
        >
          <DropdownMenu.Label className="ui-language-popover__header">
            <strong>{t("language.title", "语言")}</strong>
            <span>{t("language.interface", "界面语言")}</span>
          </DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={locale} onValueChange={selectLanguage} aria-label={languageLabel}>
            {LANGUAGE_OPTIONS.map((option) => (
              <DropdownMenu.RadioItem
                className="ui-language-option"
                key={option.value}
                value={option.value}
                textValue={option.label}
              >
                <span className="ui-language-option__name">{option.label}</span>
                <code>{option.code}</code>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          <DropdownMenu.Separator />
          <DropdownMenu.Label className="ui-language-popover__header">
            <strong>{t("currency.title", "显示货币")}</strong>
            <span>{t("currency.referenceOnly", "仅作参考换算")}</span>
          </DropdownMenu.Label>
          <DropdownMenu.RadioGroup
            value={displayCurrency}
            onValueChange={(value) => setDisplayCurrency(value as DisplayCurrencyCode)}
            aria-label={t("currency.choose", "选择显示货币")}
          >
            {CURRENCY_OPTIONS.map((option) => (
              <DropdownMenu.RadioItem
                className="ui-language-option"
                key={option.value}
                value={option.value}
                textValue={option.label}
              >
                <span className="ui-language-option__name">{t(`currency.${option.value}`, option.label)}</span>
                <code>{option.symbol} · {option.value}</code>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          <p className="ui-currency-note">
            {t("currency.settlementNote", "充值、提现、钱包账本和最终订单均以人民币结算。")}
          </p>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
      <button className={`ui-settings${compact ? " ui-settings--compact" : ""}`} type="button" onClick={toggleAppearance} aria-label={nextLabel} title={nextLabel}>
        {appearance === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        {!compact && <span>{appearance === "dark" ? t("theme.light", "浅色模式") : t("theme.dark", "深色模式")}</span>}
      </button>
    </div>
  );
}
