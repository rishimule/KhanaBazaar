// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";

import "@/app/globals.css";
import PolicyConsentGate from "@/components/PolicyConsentGate";
import RouteProgressProvider from "@/components/RouteProgressProvider";
import ServiceWorkerRegistrar from "@/components/ServiceWorkerRegistrar";
import ThirdPartyErrorSuppressor from "@/components/ThirdPartyErrorSuppressor";
import { AuthProvider } from "@/lib/AuthContext";
import { CartProvider } from "@/lib/CartContext";
import { DeliveryLocationProvider } from "@/lib/DeliveryLocationContext";
import { routing } from "@/i18n/routing";

async function resolveOperatorLocale(): Promise<string> {
  const cookieLocale = (await cookies()).get("NEXT_LOCALE")?.value;
  return routing.locales.includes(
    cookieLocale as (typeof routing.locales)[number],
  )
    ? (cookieLocale as string)
    : routing.defaultLocale;
}

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-poppins",
});

export const viewport: Viewport = {
  themeColor: "#0F6B06",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: {
    default: "Khana Bazaar — Operator",
    template: "%s | Khana Bazaar",
  },
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512x512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: { url: "/icons/icon-180x180.png", sizes: "180x180", type: "image/png" },
  },
};

export default async function OperatorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await resolveOperatorLocale();
  const messages = (await import(`../../../messages/${locale}.json`)).default;

  return (
    <html lang={locale} className={poppins.variable}>
      <head>
        <ThirdPartyErrorSuppressor />
        <link rel="manifest" href="/manifest.json" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body>
        <RouteProgressProvider>
          <NextIntlClientProvider locale={locale} messages={messages}>
            <AuthProvider>
              <PolicyConsentGate />
              <DeliveryLocationProvider>
                <CartProvider>
                  <main>{children}</main>
                </CartProvider>
              </DeliveryLocationProvider>
            </AuthProvider>
          </NextIntlClientProvider>
        </RouteProgressProvider>
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}
