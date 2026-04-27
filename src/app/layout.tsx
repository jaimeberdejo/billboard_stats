import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const spaceGrotesk = localFont({
  src: "./SpaceGrotesk-Variable.ttf",
  variable: "--font-space-grotesk",
  display: "swap",
  weight: "300 700",
  fallback: ["Arial", "Helvetica", "sans-serif"],
});

export const metadata: Metadata = {
  title: "Billboard Stats",
  description: "Billboard Hot 100 and Billboard 200 history, movement, and records.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans text-[13px]">
        {children}
      </body>
    </html>
  );
}
