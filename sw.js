// 앱 파일을 캐시에 넣어 두고 오프라인에서는 캐시로 연다.
// 인터넷이 되면 항상 서버의 최신 파일을 쓰므로 수정은 다음 실행 때 바로 반영된다.
// VERSION 은 예전 캐시를 지우는 용도. FILES 목록을 바꿀 때 올린다.
const VERSION = "gas-pressure-v2";
const FILES = ["./", "index.html", "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png", "icon-maskable-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 네트워크 우선, 안 되면 캐시. no-cache 로 브라우저 HTTP 캐시(Pages 는 10분)도 건너뛰고 서버에 확인한다.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request, { cache: "no-cache" })
      .then(res => {
        const copy = res.clone();
        caches.open(VERSION).then(c => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match("index.html")))
  );
});
