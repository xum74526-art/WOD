"use client";

import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { Theme } from "@radix-ui/themes";

type Appearance = "light" | "dark";

type ThemeModeContextValue = {
  appearance: Appearance;
  setAppearance: (appearance: Appearance) => void;
  toggleAppearance: () => void;
};

const ThemeModeContext = createContext<ThemeModeContextValue | null>(null);

function applyAppearance(appearance: Appearance) {
  const root = document.documentElement;
  root.classList.toggle("dark", appearance === "dark");
  root.dataset.colorMode = appearance;
  root.dataset.radius = "square";
  root.style.colorScheme = appearance;
}

export function useKaiTheme() {
  const value = useContext(ThemeModeContext);
  if (!value) throw new Error("useKaiTheme must be used inside ThemeRoot");
  return value;
}

export function ThemeRoot({ children }: { children: ReactNode }) {
  const [appearance, setAppearance] = useState<Appearance>("light");

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const saved = window.localStorage.getItem("kai.color-mode.v1");
    const initial = saved === "dark" || saved === "light" ? saved : query.matches ? "dark" : "light";
    setAppearance(initial);
    applyAppearance(initial);
    const update = (event: MediaQueryListEvent) => {
      if (window.localStorage.getItem("kai.color-mode.v1")) return;
      const next = event.matches ? "dark" : "light";
      setAppearance(next);
      applyAppearance(next);
    };
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const value = useMemo<ThemeModeContextValue>(() => ({
    appearance,
    setAppearance: (next) => {
      window.localStorage.setItem("kai.color-mode.v1", next);
      applyAppearance(next);
      setAppearance(next);
    },
    toggleAppearance: () => {
      const next = appearance === "dark" ? "light" : "dark";
      window.localStorage.setItem("kai.color-mode.v1", next);
      applyAppearance(next);
      setAppearance(next);
    },
  }), [appearance]);

  return (
    <ThemeModeContext.Provider value={value}>
      <Theme appearance={appearance} accentColor="teal" grayColor="slate" radius="none" scaling="100%">
        {children}
      </Theme>
    </ThemeModeContext.Provider>
  );
}
