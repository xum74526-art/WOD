import Image from "next/image";
import Link from "next/link";

type BrandProps = {
  inverse?: boolean;
};

export function Brand({ inverse = false }: BrandProps) {
  return (
    <Link className={`brand${inverse ? " brand--inverse" : ""}`} href="/" aria-label="返回首页">
      <Image className="brand__logo" src="/kai-logo.svg" alt="" width={72} height={32} priority />
    </Link>
  );
}
