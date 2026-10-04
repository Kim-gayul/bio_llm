import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BioLab · 나의 첫 연구 파트너",
  description: "분자생물학 석사 신입생을 위한 논문 근거 기반 OpenAI 연구 공간",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
