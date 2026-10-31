import { env } from 'cloudflare:workers';
import { runInDurableObject, runDurableObjectAlarm, evictDurableObject, reset } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import worker, { limitedText } from '../src/worker';
import type { State } from '../src/bot';
const chat = (id: number) => env.CHATS.getByName('private:' + id);
const update = (chatId: number, id: number, text: string) => ({ update_id: id, message: { chat: { id: chatId, type: 'private' }, from: { id: chatId, is_bot: false }, text } });
const read = (id: number) => runInDurableObject(chat(id), (_obj, ctx) => {
  const row = ctx.storage.sql.exec<{ body: string }>('SELECT body FROM state WHERE id=1').toArray()[0];
  return row ? JSON.parse(row.body) as State : null;
});
const post = (body: unknown, secret = env.WEBHOOK_SECRET) => worker.fetch(new Request('https://bot.example/telegram/webhook', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': secret }, body: JSON.stringify(body) }), env);
beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json({ ok: true, result: { message_id: 1 } }))); });
afterEach(async () => { await reset(); vi.unstubAllGlobals(); });
describe('Webhook and real SQLite Durable Objects', () => {
  it('reads a bounded API response stream', async () => { expect(JSON.parse(await limitedText(Response.json({ ok: true }).body))).toEqual({ ok: true }); });
  it('rejects missing/wrong authentication before storing anything', async () => { expect((await post(update(1, 1, '/start'), '')).status).toBe(403); expect((await read(1))).toBeNull(); });
  it('ignores groups and sender mismatch', async () => {
    const a = update(1, 1, '/start'); a.message.chat.type = 'group'; expect((await post(a)).status).toBe(200);
    const b = update(1, 2, '/start'); b.message.from.id = 2; await post(b); expect(await read(1)).toBeNull();
  });
  it('ignores non-started users', async () => { await post(update(1, 1, '/nuevo Revisar')); expect(await read(1)).toBeNull(); });
  it('rejects malformed and oversized authenticated payloads', async () => {
    const request = new Request('https://bot.example/telegram/webhook', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': env.WEBHOOK_SECRET }, body: 'x'.repeat(17_000) }); expect((await worker.fetch(request, env)).status).toBe(400);
  });
  it('isolates tasks between two conversations', async () => {
    await post(update(1, 1, '/start')); await post(update(2, 2, '/start')); await post(update(1, 3, '/nuevo First task')); await post(update(1, 4, '/nuevo Reserved task')); await post(update(2, 5, '/hecho 2'));
    expect((await read(1))?.tasks).toHaveLength(2); expect((await read(2))?.tasks).toHaveLength(0); expect(JSON.stringify(await read(2))).not.toContain('Reserved task');
  });
  it('deduplicates concurrent repeated updates atomically', async () => {
    await post(update(1, 1, '/start')); await Promise.all([post(update(1, 2, '/nuevo Revisar')), post(update(1, 2, '/nuevo Revisar'))]); expect((await read(1))?.tasks).toHaveLength(1);
  });
  it('keeps task state across object eviction', async () => {
    await post(update(1, 1, '/start')); await post(update(1, 2, '/nuevo Persistent task')); await evictDurableObject(chat(1)); expect((await read(1))?.tasks[0].title).toBe('Persistent task');
  });
  it('rejects chat scope changes even via a binding', async () => { await chat(1).accept(update(1, 1, '/start')); await chat(1).accept(update(2, 2, '/nuevo injected')); expect((await read(1))?.tasks).toHaveLength(0); });
  it('enforces rate limits but permits deletion', async () => {
    await post(update(1, 1, '/start')); for (let i = 2; i < 20; i++) await post(update(1, i, '/nuevo Revisar')); expect((await read(1))?.tasks.length).toBe(14); await post(update(1, 20, '/borrar confirmar')); expect((await read(1))?.active).toBe(false);
  });
  it('never saves interview text or file contents', async () => {
    await post(update(1, 1, '/start')); await post(update(1, 2, '/entrevista b1b2')); await post(update(1, 3, 'SECRET_RESPONSE_SENTINEL')); const a = update(1, 4, ''); Object.assign(a.message, { document: { file_id: 'PRIVATE_FILE_SENTINEL' } }); await post(a); const s = JSON.stringify(await read(1)); expect(s).not.toContain('SECRET_RESPONSE'); expect(s).not.toContain('PRIVATE_FILE');
  });
  it('alarm sends queued replies then removes confirmed data', async () => {
    await post(update(1, 1, '/start')); await runDurableObjectAlarm(chat(1)); expect(fetch).toHaveBeenCalled(); expect((await read(1))?.outbox).toHaveLength(0);
  });
  it('holds ambiguous sends without retry after eviction', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('network outcome unknown'));
    await post(update(1, 1, '/start')); await runDurableObjectAlarm(chat(1)); expect((await read(1))?.outbox[0].status).toBe('unknown'); const count = vi.mocked(fetch).mock.calls.length; await evictDurableObject(chat(1)); await post(update(1, 2, '/pendientes')); await runDurableObjectAlarm(chat(1)); expect(vi.mocked(fetch).mock.calls.length).toBe(count + 1);
  }, 15_000);
  it('retries only an explicit 429 after retry_after', async () => {
    vi.mocked(fetch).mockImplementation(async () => Response.json({ ok: false, error_code: 429, parameters: { retry_after: 30 } }, { status: 429 }));
    await post(update(1, 1, '/start')); const before = Date.now(); await runDurableObjectAlarm(chat(1)); const item = (await read(1))!.outbox[0]; expect(item.status).toBe('pending'); expect(item.due).toBeGreaterThanOrEqual(before + 30_000);
  });
  it('blocked bot disables reminders and does not retry', async () => {
    await post(update(1, 1, '/start')); await post(update(1, 2, '/avisos activar')); vi.mocked(fetch).mockImplementation(async () => Response.json({ ok: false, error_code: 403 }, { status: 403 })); await runDurableObjectAlarm(chat(1)); expect((await read(1))?.alerts).toBe(false); expect((await read(1))?.outbox).toHaveLength(0);
  });
  it('deletion removes active records after confirmation delivery', async () => {
    await post(update(1, 1, '/start')); await post(update(1, 2, '/nuevo Delete me')); await post(update(1, 3, '/borrar confirmar')); await runDurableObjectAlarm(chat(1)); expect(await read(1)).toBeNull();
  });
  it('publishes privacy and health without exposing state or secrets', async () => {
    const health = await worker.fetch(new Request('https://bot.example/health'), env); expect(health.status).toBe(200); expect(await health.text()).not.toContain(env.WEBHOOK_SECRET);
    const policy = await worker.fetch(new Request('https://bot.example/privacidad'), env); expect(await policy.text()).toContain('Cloudflare'); expect((await worker.fetch(new Request('https://bot.example/admin'), env)).status).toBe(404);
  });
});
