"use client";

import Link from "next/link";
import { SimplePage } from "@/components/simple-page";
import { useI18n } from "@/components/locale-root";

export default function PrivacyPage() {
  const { locale } = useI18n();
  return <SimplePage title="隐私说明" titleEn="Privacy Notice" description="正式隐私政策需要结合网站主体、数据范围和 Kai 登录授权范围完成法务审核。" descriptionEn="The formal privacy policy requires legal review of the website operator, data scope, and Kai authorization scope."
    body="你可以在账号注销页面查看未结事项并申请注销 WOD 账号。注销完成后，登录会话和 Kai 登录关联失效，个人资料及可删除数据会被清理；履约、争议、审计或法定义务确需保留的记录仅在必要范围内受限保存。注销 WOD 不会注销外部 Kai 账号。无需重新安装 App 即可申请。"
    bodyEn="You can check outstanding items and request WOD account deletion on the account-deletion page. On completion, WOD sign-in sessions and the linked Kai sign-in are disabled, and personal profile data and other deletable data are cleared. Records needed for obligations, disputes, audit or legal duties are retained only as necessary with restricted access. This does not delete your external Kai account. You do not need to reinstall the app.">
    <p><Link href="/account-deletion">{locale === "en" ? "Request WOD account deletion" : "申请注销 WOD 账号"}</Link></p>
  </SimplePage>;
}
