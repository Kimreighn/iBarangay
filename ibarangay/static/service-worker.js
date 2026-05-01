const DEFAULT_ICON = '/static/default-avatar.svg';

self.addEventListener('install', event => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim());
});

async function hasOpenAppClient() {
    const clients = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true
    });

    return clients.some(client => {
        try {
            return new URL(client.url).origin === self.location.origin;
        } catch (error) {
            return false;
        }
    });
}

self.addEventListener('push', event => {
    event.waitUntil((async () => {
        let payload = {};

        try {
            payload = event.data ? event.data.json() : {};
        } catch (error) {
            const text = event.data ? await event.data.text() : '';
            payload = { body: text };
        }

        if (await hasOpenAppClient()) {
            return;
        }

        const title = payload.title || 'iBarangay Alert';
        await self.registration.showNotification(title, {
            body: payload.body || 'New barangay update received.',
            icon: payload.icon || DEFAULT_ICON,
            badge: payload.badge || DEFAULT_ICON,
            tag: payload.tag || `ibarangay-${payload.eventKey || 'alert'}`,
            requireInteraction: Boolean(payload.requireInteraction),
            renotify: true,
            vibrate: Array.isArray(payload.vibrate) ? payload.vibrate : [120, 60, 120],
            data: {
                url: payload.url || '/dashboard',
                eventKey: payload.eventKey || '',
            }
        });
    })());
});

self.addEventListener('notificationclick', event => {
    event.notification.close();

    event.waitUntil((async () => {
        const rawUrl = event.notification.data && event.notification.data.url
            ? event.notification.data.url
            : '/dashboard';
        const targetUrl = new URL(rawUrl, self.location.origin).href;
        const windowClients = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        });

        for (const client of windowClients) {
            if (client.url === targetUrl && 'focus' in client) {
                return client.focus();
            }
        }

        const sameOriginClient = windowClients.find(client => {
            try {
                return new URL(client.url).origin === self.location.origin;
            } catch (error) {
                return false;
            }
        });

        if (sameOriginClient && 'navigate' in sameOriginClient) {
            await sameOriginClient.navigate(targetUrl);
            if ('focus' in sameOriginClient) {
                return sameOriginClient.focus();
            }
        }

        if (self.clients.openWindow) {
            return self.clients.openWindow(targetUrl);
        }

        return null;
    })());
});
