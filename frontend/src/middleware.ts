// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  matcher: [
    "/((?!api|_next|seller|admin|dev-logs|favicon\\.ico|icons|manifest\\.json|sw\\.js|.*\\.(?:png|jpg|jpeg|svg|webp|ico)).*)",
  ],
};
