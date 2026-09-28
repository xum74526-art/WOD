import type { Metadata } from "next";
import { AdminCouponWorkspace } from "@/components/admin-coupon-workspace";

export const metadata: Metadata = { title: "优惠券活动 · 管理控制台" };

export default function AdminCouponsPage() {
  return <AdminCouponWorkspace/>;
}
