"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Megaphone, X } from "@phosphor-icons/react";
import { useI18n } from "@/components/locale-root";
import { getMajorAnnouncement, type MajorAnnouncement } from "@/lib/internal-api";
import { notificationActionPath } from "@/lib/notification-navigation";
import { toTraditionalChinese } from "@/lib/traditional-chinese";

const DISMISSED_ANNOUNCEMENT_KEY = "kai-major-announcement-dismissed:v1";

function dismissedAnnouncementId(): number | null {
  try {
    const value = Number(window.localStorage.getItem(DISMISSED_ANNOUNCEMENT_KEY));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function MajorAnnouncementBanner() {
  const { locale, t } = useI18n();
  const [announcement, setAnnouncement] = useState<MajorAnnouncement | null>(null);

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

  function dismiss() {
    if (!announcement) return;
    try { window.localStorage.setItem(DISMISSED_ANNOUNCEMENT_KEY, String(announcement.id)); } catch { /* hidden for this visit */ }
    setAnnouncement(null);
  }

  if (!announcement || !copy) return null;

  return <aside className="home-major-announcement" aria-labelledby={`major-announcement-${announcement.id}`}>
    <span className="home-major-announcement__icon" aria-hidden="true"><Megaphone size={21} weight="duotone" /></span>
    <div className="home-major-announcement__copy">
      <small>{t("majorAnnouncement.label", "重大公告")}</small>
      <strong id={`major-announcement-${announcement.id}`}>{copy.title}</strong>
      <p>{copy.content}</p>
    </div>
    {actionPath && <Link className="home-major-announcement__action" href={actionPath}>
      {t("majorAnnouncement.view", "查看详情")}<ArrowRight size={15} />
    </Link>}
    <button type="button" className="home-major-announcement__dismiss" onClick={dismiss} aria-label={t("majorAnnouncement.dismiss", "关闭重大公告")}>
      <X size={16} />
    </button>
  </aside>;
}
