// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import "@/app/globals.css";
import CartSyncBanner from "@/components/CartSyncBanner";
import Footer from "@/components/Footer";
import Navbar from "@/components/Navbar";
import RouteProgressProvider from "@/components/RouteProgressProvider";
import ThirdPartyErrorSuppressor from "@/components/ThirdPartyErrorSuppressor";
import { AuthProvider } from "@/lib/AuthContext";
import { CartProvider } from "@/lib/CartContext";
import { FavoritesProvider } from "@/lib/FavoritesContext";
import { CustomerAddressesProvider } from "@/lib/CustomerAddressesContext";
import { DeliveryLocationAutoSync } from "@/components/DeliveryLocationAutoSync";
import { DeliveryLocationProvider } from "@/lib/DeliveryLocationContext";
import { SearchOverlayProvider } from "@/lib/SearchOverlayContext";
import { alternateLanguages } from "@/i18n/metadata";
import { routing } from "@/i18n/routing";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-poppins",
});

export const viewport: Viewport = {
  themeColor: "#B8470F",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: {
    default: "Khana Bazaar — Your Hyperlocal Indian Marketplace",
    template: "%s | Khana Bazaar",
  },
  description:
    "Shop groceries & essentials from nearby local stores. Pay seamlessly with UPI. Khana Bazaar connects you to your neighborhood sellers.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Khana Bazaar",
  },
  icons: {
    icon: "/icons/icon-192x192.png",
    apple: "/icons/icon-192x192.png",
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

  return (
    <html lang={locale} className={poppins.variable}>
      <head>
        <ThirdPartyErrorSuppressor />
        <link rel="manifest" href="/manifest.json" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body className="kb-customer-root">
        <RouteProgressProvider>
          <NextIntlClientProvider messages={messages}>
            <AuthProvider>
              <DeliveryLocationProvider>
                <CustomerAddressesProvider>
                  <DeliveryLocationAutoSync />
                  <FavoritesProvider>
                    <CartProvider>
                      <SearchOverlayProvider>
                        <Navbar />
                      </SearchOverlayProvider>
                      <CartSyncBanner />
                      <main>{children}</main>
                      <Footer />
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

function ServiceWorkerRegistrar() {
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `
          if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
              navigator.serviceWorker.register('/sw.js').catch(() => {});
            });
          }
        `,
      }}
    />
  );
}
