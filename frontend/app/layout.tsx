import type { Metadata, Viewport } from "next";
import "./globals.css";
import PwaRegister from "../components/pwa/PwaRegister";

export const viewport: Viewport = {
  themeColor: "#0284c7",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: "Pannaga - Hyperlocal Monsoon Prediction",
  description: "Hyperlocal Monsoon Onset & Break Prediction System for India",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Pannaga",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 antialiased selection:bg-sky-500 selection:text-white">
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
