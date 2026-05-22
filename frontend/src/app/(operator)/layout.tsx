// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";

import "@/app/globals.css";
import RouteProgressProvider from "@/components/RouteProgressProvider";
import ThirdPartyErrorSuppressor from "@/components/ThirdPartyErrorSuppressor";
import { AuthProvider } from "@/lib/AuthContext";
import { CartProvider } from "@/lib/CartContext";
import { DeliveryLocationProvider } from "@/lib/DeliveryLocationContext";
import enMessages from "../../../messages/en.json";

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
};

export const metadata: Metadata = {
  title: {
    default: "Khana Bazaar — Operator",
    template: "%s | Khana Bazaar",
  },
  manifest: "/manifest.json",
  icons: {
    icon: "/icons/icon-192x192.png",
    apple: "/icons/icon-192x192.png",
  },
};

export default function OperatorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={poppins.variable}>
      <head>
        <ThirdPartyErrorSuppressor />
        <link rel="manifest" href="/manifest.json" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body>
        <RouteProgressProvider>
          <NextIntlClientProvider locale="en" messages={enMessages}>
            <AuthProvider>
              <DeliveryLocationProvider>
                <CartProvider>
                  <main>{children}</main>
                </CartProvider>
              </DeliveryLocationProvider>
            </AuthProvider>
          </NextIntlClientProvider>
        </RouteProgressProvider>
      </body>
    </html>
  );
}
