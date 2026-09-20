"use client";

import styles from "@/components/contact-phone.module.css";
import { useI18n } from "@/components/locale-root";

export function ContactPhone() {
  const { t } = useI18n();
  return <a className={styles.phone} href="tel:+864001082026">{t("contact.phoneLabel", "联系我们：{phone}", { phone: "+86 4001082026" })}</a>;
}
