const CACHE = "urdu-book-v5";
const SHELL = [
  "./", "./index.html", "./manifest.json", "./icon.svg",
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
  "https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;600&display=swap"
];
const API = ["status", "highlights", "bookmarks", "upload", "delete"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL).catch(err => console.warn("cache fail", err))));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  const last = url.pathname.split('/').pop();
  if (API.includes(last)) return;
  if (last === "book.pdf") {
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) caches.open(CACHE).then(c => c.put(e.request, r.clone())).catch(()=>{});
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    if (resp.ok) caches.open(CACHE).then(c => c.put(e.request, resp.clone())).catch(()=>{});
    return resp;
  }).catch(() => caches.match("./index.html"))));
});
