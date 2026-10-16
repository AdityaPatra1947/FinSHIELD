import Link from "next/link";

export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 2 28 6.5v9c0 7.2-5 12.4-12 14.5C9 27.900 4 22.700 4 15.500v-9Z" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
      <path d="M9 19l4-4.500 3 3 6-7" fill="none" stroke="#EF8557" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="brand" aria-label="FinShield home">
      <Mark /> FINSHIELD
    </Link>
  );
}
