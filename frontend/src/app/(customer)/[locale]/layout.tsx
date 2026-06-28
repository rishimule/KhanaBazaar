// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import "@/app/globals.css";
import CartSyncBanner from "@/components/CartSyncBanner";
import FooterGate from "@/components/FooterGate";
import Navbar from "@/components/Navbar";
import PolicyConsentGate from "@/components/PolicyConsentGate";
import RouteProgressProvider from "@/components/RouteProgressProvider";
import ServiceWorkerRegistrar from "@/components/ServiceWorkerRegistrar";
import ThirdPartyErrorSuppressor from "@/components/ThirdPartyErrorSuppressor";
import { AuthProvider } from "@/lib/AuthContext";
import { CartProvider } from "@/lib/CartContext";
import { NotificationProvider } from "@/lib/NotificationContext";
import PWAInstallProvider from "@/components/pwa/PWAInstallProvider";
import { FavoritesProvider } from "@/lib/FavoritesContext";
import { CustomerAddressesProvider } from "@/lib/CustomerAddressesContext";
import { DeliveryLocationAutoSync } from "@/components/DeliveryLocationAutoSync";
import { DeliveryLocationProvider } from "@/lib/DeliveryLocationContext";
import { SearchOverlayProvider } from "@/lib/SearchOverlayContext";
import { alternateLanguages } from "@/i18n/metadata";
import { routing } from "@/i18n/routing";
import { COMPANY_NAME } from "@/lib/brand";

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
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: {
    default: `${COMPANY_NAME} — Your Hyperlocal Indian Marketplace`,
    template: `%s | ${COMPANY_NAME}`,
  },
  description: `Shop groceries & essentials from nearby local stores. Pay seamlessly with UPI. ${COMPANY_NAME} connects you to your neighborhood sellers.`,
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: COMPANY_NAME,
  },
  icons: {
    icon: [
      { url: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512x512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: { url: "/icons/icon-180x180.png", sizes: "180x180", type: "image/png" },
  },
  alternates: {
    languages: alternateLanguages("/"),
  },
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function CustomerLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as (typeof routing.locales)[number])) {
    notFound();
  }
  setRequestLocale(locale);
  const messages = await getMessages();
  const tShared = await getTranslations("Shared");

  return (
    <html lang={locale} className={poppins.variable}>
      <head>
        <ThirdPartyErrorSuppressor />
        <link rel="manifest" href="/manifest.webmanifest" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body className="kb-customer-root">
        <a href="#main" className="skip-link">{tShared("skipToContent")}</a>
        <RouteProgressProvider>
          <NextIntlClientProvider messages={messages}>
            <AuthProvider>
              <PolicyConsentGate />
              <DeliveryLocationProvider>
                <CustomerAddressesProvider>
                  <DeliveryLocationAutoSync />
                  <FavoritesProvider>
                    <CartProvider>
                      <PWAInstallProvider>
                        <NotificationProvider>
                          <SearchOverlayProvider>
                            <Navbar />
                          </SearchOverlayProvider>
                          <CartSyncBanner />
                          <main id="main">{children}</main>
                          <FooterGate />
                        </NotificationProvider>
                      </PWAInstallProvider>
                    </CartProvider>
                  </FavoritesProvider>
                </CustomerAddressesProvider>
              </DeliveryLocationProvider>
            </AuthProvider>
          </NextIntlClientProvider>
        </RouteProgressProvider>
        <ServiceWorkerRegistrar />
      </body>
    </html>
  );
}

