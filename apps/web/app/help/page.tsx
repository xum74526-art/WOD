import type { Metadata } from "next";
import { cookies } from "next/headers";
import { SimplePage } from "@/components/simple-page";

export async function generateMetadata(): Promise<Metadata> {
  const english = (await cookies()).get("kai.locale")?.value === "en";
  return {
    title: { absolute: english ? "KAI星算 Sign-in Help" : "登入幫助 | KAI星算" },
    description: english ? "Guidance for phone and Kai SSO access." : "手機號密碼與 Kai 統一身份登入指引。",
  };
}

export default function HelpPage() {
  return <SimplePage
    title="登录帮助"
    titleEn="Sign-in Help"
    description="使用手机号密码或 Kai 统一身份登录KAI星算账户。"
    descriptionEn="Use a phone number and password or Kai SSO to access a KAI星算 account."
    body="手机号账户请使用注册号码和密码登录。首次成功使用 Kai 统一身份登录或注册时，系统会按该 Kai 身份创建本地账号，不会按邮箱或手机号合并既有账号；登录后可在账户设置中自愿设置手机号登录标识、密码和找回邮箱。当前没有短信验证，手机号不代表已核验归属。已有本地账号如需关联 Kai，请先登录后在账户设置完成绑定。"
    bodyEn="For phone access, sign in with the registered number and password. A first successful Kai SSO sign-in or registration creates a local account for that Kai identity and never merges an existing account by email or phone. After signing in, you may set a local mobile sign-in identifier, password, and recovery email in Account Settings. SMS verification is not currently available, so a mobile number does not prove ownership. To link Kai to an existing local account, sign in first and complete linking in Account Settings."
  />;
}
