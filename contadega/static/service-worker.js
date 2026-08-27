/* ContAdega PWA: somente a shell pública versionada é persistida. */
const VERSION='contadega-static-v3';
const PUBLIC=['/offline','/static/style.css','/static/app.js','/static/offline.js','/static/icons/icon.svg','/static/manifest.webmanifest'];
self.addEventListener('install',event=>event.waitUntil(caches.open(VERSION).then(cache=>cache.addAll(PUBLIC)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('contadega-')&&key!==VERSION).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==location.origin)return;
  if(url.pathname.startsWith('/api/')||request.headers.get('accept')?.includes('application/json'))return;
  if(url.pathname.startsWith('/static/')&&PUBLIC.includes(url.pathname)){
    event.respondWith(caches.match(request).then(hit=>hit||fetch(request))); return;
  }
  if(request.mode==='navigate')event.respondWith(fetch(request).catch(()=>caches.match('/offline')));
});
