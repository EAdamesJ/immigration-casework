#!/usr/bin/env python3
"""Register an already-deployed Ruta Consular Worker without persisting credentials."""
import argparse
import getpass
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-url', required=True)
    parser.add_argument('--expected-username', default='RutaConsularBot')
    parser.add_argument('--health-verified', action='store_true', help='Skip the local HTTP probe only after independently checking /health; Telegram delivery still needs verification.')
    args = parser.parse_args()
    origin = urllib.parse.urlsplit(args.worker_url)
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/') or origin.port not in (None, 443):
        parser.error('Use the public HTTPS Worker origin without credentials, query, or path.')
    base = args.worker_url.rstrip('/')
    opener = urllib.request.build_opener(NoRedirect())
    token = getpass.getpass('Existing Telegram bot token (hidden): ').strip()
    secret = getpass.getpass('Cloudflare WEBHOOK_SECRET (hidden): ').strip()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
        print('Invalid credential format; nothing registered.', file=sys.stderr)
        return 2

    def request(url, data=None, headers=None):
        raw = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(url, data=raw, headers=headers or ({'Content-Type': 'application/json'} if raw else {}))
        with opener.open(req, timeout=20) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError()
        return payload

    def api(method, data=None):
        result = json.loads(request('https://api.telegram.org/bot' + token + '/' + method, data or {}))
        if result.get('ok') is not True:
            raise ValueError()
        return result['result']

    try:
        if api('getMe').get('username', '').lower() != args.expected_username.lower():
            raise ValueError()
        if not args.health_verified:
            health = json.loads(request(base + '/health'))
            if health.get('service') != 'ruta-consular' or health.get('ready') is not True:
                raise ValueError()
            # A synthetic group update must be accepted but must not generate a reply.
            probe = {'update_id': 0, 'message': {'chat': {'id': -1, 'type': 'group'}, 'from': {'id': 1, 'is_bot': False}, 'text': '/start'}}
            if request(base + '/telegram/webhook', probe, {'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': secret}) != b'OK':
                raise ValueError()
        webhook = base + '/telegram/webhook'
        api('setWebhook', {'url': webhook, 'secret_token': secret, 'allowed_updates': ['message'], 'max_connections': 1, 'drop_pending_updates': False})
        status = api('getWebhookInfo')
        if status.get('url') != webhook:
            raise ValueError()
        print(json.dumps({'status': 'webhook_verified', 'username': args.expected_username, 'url': webhook,
                          'pending_update_count': status.get('pending_update_count'), 'max_connections': status.get('max_connections'),
                          'last_error_present': bool(status.get('last_error_date')), 'worker_probe_skipped': args.health_verified,
                          'personal_message_delivery_tested': False}))
        return 0
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        print('Webhook configuration failed. Check Worker health, account configuration and credentials. Secret values and response bodies are omitted.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
