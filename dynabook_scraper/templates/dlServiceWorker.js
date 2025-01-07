importScripts('https://unpkg.com/client-zip@2.4.6/worker.js');

async function* fileDownloadGenerator(payload) {
    for (const item of payload) {
        let response = await fetch(item.url);

        if (!response.ok) {
            console.warn(`Failed to download ${item.url}`)
            continue;
        }

        console.debug(`Fetched ${item.url}`)
        const result = {
            input: response,
            ...item,
        };
        yield result;
    }
}

self.addEventListener('activate', function () {
    clients.claim();
    console.log('Service worker activated');
});

self.addEventListener("fetch", async (event) => {
        const url = new URL(event.request.url)
        // This will intercept all request with a URL starting in /product/downloadDrivers/
        const [, name] = url.pathname.match(/\/product\/downloadDrivers\/(.+)/i) || [,]

        if (url.origin === self.origin && name) {
            // Workaround for Firefox which seems to shut down service workers after a while
            if (name === "keepalive") {
                event.respondWith(new Response("OK", {status: 200}))
                return
            }

            console.log(`Service worker download request: ${name}`)

            event.respondWith((async () => {
                const form = await event.request.formData()
                const metadata = JSON.parse(form.get("payload"))

                return downloadZip(
                    fileDownloadGenerator(metadata),
                    {metadata}
                )
            })());

        }
    }
);

console.log("Service worker loaded");