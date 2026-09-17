import type { Metadata } from "next";
import { cookies } from "next/headers";
import { SimplePage } from "@/components/simple-page";

export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get("kai.locale")?.value === "en";
  return {
    title: { absolute: english ? "算力星图 Sign-in Help" : "登入幫助 | 算力星图" },
    description: english ? "Guidance for phone and Kai SSO access." : "手機號密碼與 Kai 統一身份登入指引。",
  };
}

export default function HelpPage() {
  return <SimplePage
    title="登录帮助"
    titleEn="Sign-in Help"
    description="使用手机号密码或 Kai 统一身份登录同一个算力星图账户。"
    descriptionEn="Use a phone number and password or Kai SSO to access the same 算力星图 account."
    body="手机号账户请使用注册号码和密码登录。绑定 Kai 统一身份时，请先登录现有账户，再到账户设置完成绑定，避免创建重复账户；需要协助时可进入帮助与客服提交问题。"
    bodyEn="For phone access, sign in with the registered number and password. To link Kai SSO, sign in to your existing account first and complete the link in Account Settings to avoid a duplicate account. Open Help & Support whenever you need assistance."
  />;
}
