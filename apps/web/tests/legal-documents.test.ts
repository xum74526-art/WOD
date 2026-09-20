import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  LEGAL_ICP_FILING,
  LEGAL_OPERATOR,
  LEGAL_OPERATOR_ADDRESS,
  toTraditionalLegalText,
} from "../lib/legal-text.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("privacy policy is a versioned trilingual disclosure matching implemented data flows", () => {
  const privacy = read("../app/privacy/page.tsx");
  const renderer = read("../components/legal-document.tsx");
  const legalText = read("../lib/legal-text.ts");
  const source = privacy + renderer + legalText;

  for (const required of [
    "锆芯期算人工智能科技（上海）有限公司",
    "上海市浦东新区川南奉公路5058号3幢一层（集中登记地）",
    "沪ICP备2026046279号-1",
    "2026-09-18",
    'LEGAL_VERSION = "1.2"',
    "联系我们：+86 4001082026",
    "邮箱找回",
    "KAI 身份关联",
    "授权范围内的邮箱、姓名和头像",
    "Tesseract",
    "银行卡",
    "SSH",
    "DCloud uni-app 基础运行框架",
    "OAID",
    "阿里云中国香港区域",
    "cn-hongkong",
    "所有地区的用户",
    "香港存储、处理与必要传输",
    "单独同意",
    "算力技术社区",
    "网易 163 邮件服务",
    "七相支付（Qixiang Pay）",
    "收银台返回仅用于触发平台向服务端查单，不作为入账凭证",
    "不等于银行四要素认证或自动出款",
    "30 分钟",
    "7 天",
    "未成年人保护",
  ]) assert.match(source, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  assert.match(renderer, /locale === "zh-Hant" \? toTraditionalLegalText/);
  assert.match(privacy, /"zh-Hant": \{/);
  assert.match(privacy, /"zh-Hans": \{/);
  assert.match(privacy, /en: \{/);
  assert.match(renderer, /href="tel:\+864001082026"/);
  assert.doesNotMatch(privacy, /个人信息主要在中华人民共和国境内存储|Data is generally stored on servers in mainland China/);
  assert.doesNotMatch(source, /access@kai\.com|mailto:|正式隐私政策需要|上线前公布|Formal privacy policy requires/);
});

test("terms describe capability-gated matching, direct trade, top-up, and manual withdrawal", () => {
  const terms = read("../app/terms/page.tsx");
  for (const required of [
    "服务端能力和当前客户端构建同时启用",
    "不构成投资建议",
    "即时库存",
    "SSH",
    "充值取得的卡时仅可用于平台消费",
    "收银台返回页、客户端提示或第三方参数本身均不证明支付成功",
    "按原支付渠道处理",
    "人工转账",
    "不等于银行四要素认证或自动出款",
    "账号注销",
    "中华人民共和国大陆地区法律",
  ]) assert.match(terms, new RegExp(required.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(terms, /正式用户协议需要|The formal terms must|access@kai\.com|mailto:/);
});

test("public legal shell and contact surface use 算力星图 and expose no public email", () => {
  const simple = read("../components/simple-page.tsx");
  const contact = read("../app/contact/page.tsx");
  const footer = read("../components/site-footer.tsx");
  assert.match(simple, />算力星图 \/ INFORMATION</);
  assert.doesNotMatch(simple, /北斗 kai \/ INFORMATION|ZTW \/ INFORMATION|KAI \/ INFORMATION/);
  assert.match(contact, /<ContactPhone\s*\/>/);
  for (const source of [contact, footer]) assert.doesNotMatch(source, /access@kai\.com|mailto:/);
});

test("Traditional copy never converts registered legal identifiers", () => {
  const converted = toTraditionalLegalText(`运营主体：${LEGAL_OPERATOR}；地址：${LEGAL_OPERATOR_ADDRESS}；备案：${LEGAL_ICP_FILING}`);
  assert.match(converted, /運營主體/);
  for (const legalValue of [LEGAL_OPERATOR, LEGAL_OPERATOR_ADDRESS, LEGAL_ICP_FILING]) {
    assert.equal(converted.includes(legalValue), true);
  }
  assert.doesNotMatch(converted, /鋯芯|浦東新區|滬ICP備/);
});
