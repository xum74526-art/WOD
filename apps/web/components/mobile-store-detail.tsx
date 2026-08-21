"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Cpu, MapPin, Star, Storefront } from "@phosphor-icons/react";
import { getMobileStore, type MobileStore } from "@/lib/mobile-business-api";
import { errorMessage } from "@/lib/commerce-ui";

export function MobileStoreDetail({ id }: { id: number }) {
  const [data, setData] = useState<MobileStore | null>(null); const [error, setError] = useState("");
  useEffect(() => { getMobileStore(id).then(setData).catch((reason) => setError(errorMessage(reason))); }, [id]);
  return <section className="mobile-store-page"><Link className="store-back" href="/market"><ArrowLeft/>返回算力市场</Link>{error && <div className="commerce-error">{error}</div>}{!data && !error ? <div className="workspace-skeleton"/> : data && <><header className="mobile-store-hero"><Storefront size={44}/><div><small>VERIFIED COMPUTE SUPPLIER</small><h1>{data.supplier.company_name}</h1><p>{data.supplier.desc || "该商家暂未填写介绍。"}</p></div><aside><span><Star weight="fill"/> {Number(data.supplier.rating || 0).toFixed(1)}</span><strong>{data.supplier.order_count || 0}</strong><small>累计订单</small></aside></header><div className="store-contact-strip"><span><MapPin/>{data.supplier.region || "未标注地区"}</span><span>联系人：{data.supplier.contact}</span><span>联系电话：{data.supplier.phone}</span></div><section className="store-product-section"><header><div><small>AVAILABLE PRODUCTS</small><h2>商家算力商品</h2></div><b>{data.products.length}</b></header><div>{data.products.map((product) => <article key={product.id}><Cpu size={24}/><span><strong>{product.name}</strong><small>{product.gpu_model} · {product.memory} · {product.region_name || product.region_code || "地区未标注"}</small></span><b>{Number(product.price).toFixed(2)} 卡时/h</b><em>库存 {product.stock || 0}</em><Link href={`/market/products/${product.id}`}>{product.purchasable ? "立即购买" : "查看详情"}</Link></article>)}</div></section></>}</section>;
}
