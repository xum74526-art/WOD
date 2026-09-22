"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CalendarDots, X } from "@phosphor-icons/react";
import { useI18n } from "@/components/locale-root";
import { getMajorAnnouncement, type MajorAnnouncement } from "@/lib/internal-api";
import { notificationActionPath } from "@/lib/notification-navigation";
import { toTraditionalChinese } from "@/lib/traditional-chinese";

const DISMISSED_ANNOUNCEMENT_KEY = "kai-major-announcement-dismissed:v2";

function announcementDate(value: string | null, locale: string): string | null {
  if (!value) return null;
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 16);
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function dismissedAnnouncementId(): number | null {
  try {
    const value = Number(window.localStorage.getItem(DISMISSED_ANNOUNCEMENT_KEY));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function MajorAnnouncementBanner() {
  const { dateLocale, locale, t } = useI18n();
  const [announcement, setAnnouncement] = useState<MajorAnnouncement | null>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let active = true;
    getMajorAnnouncement()
      .then((result) => {
        if (active && result && dismissedAnnouncementId() !== result.id) setAnnouncement(result);
      })
      .catch(() => {
        // A public announcement must never block the primary home experience.
      });
    return () => { active = false; };
  }, []);

  const copy = useMemo(() => {
    if (!announcement) return null;
    if (locale === "en") {
      return {
        title: announcement.title_en || announcement.title,
        content: announcement.content_en || announcement.content,
      };
    }
    if (locale === "zh-Hant") {
      return {
        title: toTraditionalChinese(announcement.title),
        content: toTraditionalChinese(announcement.content),
      };
    }
    return { title: announcement.title, content: announcement.content };
  }, [announcement, locale]);

  const actionPath = useMemo(
    () => notificationActionPath(announcement?.action_url),
    [announcement?.action_url],
  );
  const publishedAt = useMemo(
    () => announcementDate(announcement?.created_at ?? null, dateLocale),
    [announcement?.created_at, dateLocale],
  );

  const dismiss = useCallback(() => {
    if (!announcement) return;
    try { window.localStorage.setItem(DISMISSED_ANNOUNCEMENT_KEY, String(announcement.id)); } catch { /* hidden for this visit */ }
    setAnnouncement(null);
  }, [announcement]);

  useEffect(() => {
    if (!announcement) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") dismiss();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, [announcement, dismiss]);

  if (!announcement || !copy) return null;

  return <div className="home-major-announcement" role="presentation">
    <section
      ref={dialogRef}
      className="home-major-announcement__dialog"
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      aria-labelledby={`major-announcement-${announcement.id}`}
      aria-describedby={`major-announcement-content-${announcement.id}`}
    >
      <header className="home-major-announcement__header">
        <span className="home-major-announcement__rail" aria-hidden="true" />
        <div className="home-major-announcement__heading">
          <small>{t("majorAnnouncement.label", "重大公告")}</small>
          <h2 id={`major-announcement-${announcement.id}`}>{copy.title}</h2>
        </div>
        <button type="button" className="home-major-announcement__dismiss" onClick={dismiss} aria-label={t("majorAnnouncement.dismiss", "关闭重大公告")}>
          <X size={21} />
        </button>
      </header>

      {publishedAt && <div className="home-major-announcement__time">
        <CalendarDots size={17} aria-hidden="true" />
        <span>{t("majorAnnouncement.publishedAt", "发布时间")}：{publishedAt}</span>
      </div>}

      <div className="home-major-announcement__body">
        <p id={`major-announcement-content-${announcement.id}`}>{copy.content}</p>
        {actionPath && <Link className="home-major-announcement__action" href={actionPath} onClick={dismiss}>
          {t("majorAnnouncement.view", "查看相关内容")}<ArrowRight size={16} />
        </Link>}
      </div>

      <footer className="home-major-announcement__footer">
        <button type="button" className="home-major-announcement__acknowledge" onClick={dismiss}>
          {t("majorAnnouncement.acknowledge", "我知道了")}
        </button>
      </footer>
    </section>
  </div>;
}
