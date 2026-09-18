import type { Metadata } from "next";
import { ImageAttributionsContent } from "./image-attributions-content";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "圖片來源與許可 | 算力星图",
      description: "查看算力星图 GPU 圖片的原作、作者、修改方式與使用許可。",
    },
    "zh-Hans": {
      title: "图片来源与许可 | 算力星图",
      description: "查看算力星图 GPU 图片的原作、作者、修改方式与使用许可。",
    },
    en: {
      title: "Image Sources and Licenses | 算力星图",
      description: "Original works, authors, modifications and licenses for GPU images used by 算力星图.",
    },
  });
}

export default function ImageAttributionsPage() {
  return <ImageAttributionsContent />;
}
