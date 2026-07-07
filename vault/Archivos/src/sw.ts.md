/// <reference lib="WebWorker" />

import { cleanupOutdatedCaches, matchPrecache, precacheAndRoute } from "workbox-precaching";
import { registerRoute } from "workbox-routing";
import { NetworkOnly } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<string | { revision: string | null; url: string }>;
};

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const OFFLINE_URL = "/offline.html";

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

registerRoute(
  ({ url }) => url.pathname.startsWith("/api/"),
  new NetworkOnly(),
  "GET",
);

registerRoute(
  ({ request }) => WRITE_METHODS.has(request.method),
  new NetworkOnly(),
);

registerRoute(
  ({ request }) => request.mode === "navigate",
  async ({ event }) => {
    try {
      return await fetch(event.request);
    } catch {
      return (await matchPrecache(OFFLINE_URL)) ?? Response.error();
    }
  },
);

export {};
