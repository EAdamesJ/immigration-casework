import { defineConfig } from 'vitest/config';
import { cloudflareTest } from '@cloudflare/vitest-plugin';
export default defineConfig({
  plugins: [cloudflareTest({
    wrangler: { configPath: './wrangler.jsonc' },
    miniflare: { bindings: { TELEGRAM_BOT_TOKEN: '123456:' + 'fixture_only_not_a_secret'.repeat(2), WEBHOOK_SECRET: 'fixture_webhook_' + 'x'.repeat(40) } },
  })],
  test: { include: ['test/**/*.test.ts'] },
});
