const CACHE="ae-dl-v1",SHELL=["./","./AE-Downloader.html","./manifest.json","./icon.svg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",e=>{const req=e.request,url=new URL(req.url);if(req.method!=="GET"||url.pathname.startsWith("/api/")||url.origin!==location.origin)return;e.respondWith(fetch(req).then(res=>{if(res.ok)caches.open(CACHE).then(c=>c.put(req,res.clone())).catch(()=>{});return res}).catch(()=>caches.match(req,{ignoreSearch:true}).then(r=>r||caches.match("./AE-Downloader.html"))))});
