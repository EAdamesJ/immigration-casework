import { DurableObject } from 'cloudflare:workers';
import { command, DAY, initial, KEYBOARD, maintenance, nextAlarm, PRIVACY, queue, type State } from './bot';

interface Message { chat: { id: number; type: string }; from: { id: number; is_bot?: boolean }; text?: string; document?: unknown; photo?: unknown; voice?: unknown }
interface Update { update_id: number; message: Message }
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
export function privateUpdate(v: unknown): v is Update {
  if (!record(v) || !Number.isSafeInteger(v.update_id) || Number(v.update_id) < 0 || !record(v.message)) return false;
  const m = v.message;
  if (!record(m.chat) || !record(m.from) || m.chat.type !== 'private' || !Number.isSafeInteger(m.chat.id) || Number(m.chat.id) <= 0 || m.from.id !== m.chat.id || m.from.is_bot !== false) return false;
  return m.text === undefined || typeof m.text === 'string';
}
function configured(env: Env): boolean {
  return /^\d+:[A-Za-z0-9_-]{20,}$/.test(env.TELEGRAM_BOT_TOKEN ?? '') && /^[A-Za-z0-9_-]{32,256}$/.test(env.WEBHOOK_SECRET ?? '') && !!env.BOT_OPERATOR_CONTACT && env.BOT_PRIVACY_URL.startsWith('https://');
}
async function authorized(request: Request, secret: string): Promise<boolean> {
  const provided = request.headers.get('X-Telegram-Bot-Api-Secret-Token') ?? '';
  if (!secret || provided.length > 256) return false;
  const encode = new TextEncoder();
  const hashes = await Promise.all([secret, provided].map(value => crypto.subtle.digest('SHA-256', encode.encode(value))));
  return crypto.subtle.timingSafeEqual(hashes[0], hashes[1]);
}
export async function limitedText(stream: ReadableStream<Uint8Array> | null, maximum = 16_384): Promise<string> {
  if (!stream) return '';
  const reader = stream.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > maximum) { await reader.cancel(); throw new Error('payload_limit'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const all = new Uint8Array(size); let offset = 0;
  for (const c of chunks) { all.set(c, offset); offset += c.length; }
  return new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(all);
}
function reply(body: string, status = 200, type = 'text/plain; charset=utf-8'): Response {
  return new Response(body, { status, headers: { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'", 'Referrer-Policy': 'no-referrer' } });
}
const escape = (text: string) => text.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
function page(env: Env, privacy: boolean): string {
  const content = privacy ? `<h1>Privacidad de Ruta Consular</h1><p>Actualizada: 31 de octubre de 2026.</p><p>${escape(PRIVACY)}</p><h2>Qué se procesa</h2><p>Telegram entrega el identificador de chat, remitente y mensaje al webhook de Cloudflare. El bot conserva el identificador de chat, tareas genéricas, zona horaria, consentimiento de avisos, recordatorios e índice de práctica. No conserva nombres, perfiles, archivos ni respuestas de entrevista en su base. No descarga adjuntos, ni envía mensajes a un proveedor de IA.</p><h2>Para qué</h2><p>Responder a tus comandos, mantener tus pendientes y enviar únicamente los recordatorios que programes tras activar los avisos. No calcula plazos legales, consulta cuentas oficiales, decide elegibilidad ni garantiza visas.</p><h2>Proveedores y acceso</h2><p>Telegram transporta y conserva la conversación conforme a sus políticas; los chats de bots no tienen cifrado de extremo a extremo. Cloudflare aloja el webhook y el almacenamiento SQLite de Durable Objects. El operador con acceso administrativo a esa cuenta puede acceder a la información almacenada. No se garantiza residencia de datos en un país específico. Las bases no se publican en GitHub.</p><h2>Conservación y borrado</h2><p>/borrar confirmar retira tareas, zona, avisos y práctica de la base activa. Para enviar la confirmación puede conservarse temporalmente el identificador; los mensajes con entrega incierta caducan en un máximo de siete días. La deduplicación conserva identificadores técnicos de actualización hasta siete días durante el uso activo. Tras 90 días sin comandos se retiran los datos activos mediante una alarma. Los fallos o límites del proveedor pueden retrasar esa limpieza. El borrado no retira mensajes de Telegram ni supone borrado inmediato de réplicas o copias de recuperación del proveedor.</p><h2>Tus opciones</h2><p>/pendientes muestra tus tareas; /avisos desactivar cancela los recordatorios pendientes; /cancelar termina una práctica; /borrar confirmar elimina los datos activos. Un envío que ya empezó puede completarse. Gestiona el historial de Telegram desde la aplicación.</p><h2>Contacto del operador</h2><p>${escape(env.BOT_OPERATOR_CONTACT)}</p><p>Este canal público sirve para pedir un medio de contacto privado. No publiques datos personales, documentos ni identificadores en GitHub. Esta política describe la implementación; no afirma certificaciones ni cumplimiento automático de todas las leyes.</p>` : '<h1>Ruta Consular</h1><p>Tu asistente independiente para organizar pendientes y practicar entrevistas consulares.</p><p>En Telegram: <a href="https://t.me/RutaConsularBot">@RutaConsularBot</a>. Pulsa Iniciar y usa /ayuda.</p><p>Ofrece tareas personales, recordatorios voluntarios y práctica guiada B1/B2 o de inmigrante. No utiliza IA generativa ni presenta solicitudes.</p><p><a href="/privacidad">Privacidad</a> · <a href="https://github.com/EAdamesJ/immigration-casework">Código y documentación</a></p>';
  return '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ruta Consular' + (privacy ? ' · Privacidad' : '') + '</title><style>body{margin:0;background:#0b192a;color:#edf6f5;font:18px/1.65 system-ui}main{max-width:780px;margin:8vh auto;padding:28px}h1{font-size:2.3rem;line-height:1.15}h2{margin-top:2rem;font-size:1.3rem;color:#74ddd1}a{color:#74ddd1}p{overflow-wrap:anywhere}</style><main>' + content + '</main></html>';
}

export class ConsularChat extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)');
    this.ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS updates (id INTEGER PRIMARY KEY, seen INTEGER NOT NULL)');
    this.ctx.storage.sql.exec('CREATE INDEX IF NOT EXISTS updates_seen ON updates(seen)');
  }
  private read(): State | null {
    const row = this.ctx.storage.sql.exec<{ body: string }>('SELECT body FROM state WHERE id=1').toArray()[0];
    return row ? JSON.parse(row.body) as State : null;
  }
  private write(s: State): void {
    this.ctx.storage.sql.exec('INSERT INTO state(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', JSON.stringify(s));
  }
  private async arm(): Promise<void> {
    const s = this.read(), next = s ? nextAlarm(s, Date.now()) : null;
    if (next === null) {
      this.ctx.storage.sql.exec('DELETE FROM state'); this.ctx.storage.sql.exec('DELETE FROM updates');
      await this.ctx.storage.deleteAlarm();
    } else await this.ctx.storage.setAlarm(next);
  }
  async accept(value: unknown): Promise<void> {
    if (!privateUpdate(value)) return;
    const m = value.message, now = Date.now(), body = (m.text ?? '').trim();
    this.ctx.storage.transactionSync(() => {
      if (this.ctx.storage.sql.exec('SELECT id FROM updates WHERE id=?', value.update_id).toArray().length) return;
      let s = this.read();
      if (s && s.chat !== m.chat.id) return;
      if (s) maintenance(s, now);
      if (!s?.active) {
        if (!/^\/start(?:@\w+)?(?:\s|$)/i.test(body)) return;
        // Re-start preserves an existing in-flight send, not deleted tasks/practice.
        const old = s?.outbox ?? [];
        s = initial(m.chat.id, now); s.outbox = old;
      }
      this.ctx.storage.sql.exec('INSERT INTO updates(id,seen) VALUES(?,?)', value.update_id, now);
      this.ctx.storage.sql.exec('DELETE FROM updates WHERE seen<?', now - 7 * DAY);
      if (now - s.window >= 60_000) { s.window = now; s.count = 0; }
      if ((s.count >= 15 || s.outbox.length >= 50) && body !== '/borrar confirmar') { this.write(s); return; }
      s.count++; s.seen = now;
      let text: string;
      if (m.document || m.photo || m.voice) text = 'No descargo archivos aquí. Trabaja los documentos sensibles en el expediente privado. Usa /documentos.';
      else if (body.length > 4000) text = 'Usa mensajes breves y no incluyas datos sensibles.';
      else text = command(s, body, now, { contact: this.env.BOT_OPERATOR_CONTACT, privacy: this.env.BOT_PRIVACY_URL });
      queue(s, text, now); this.write(s);
    });
    // A retry after a crash between commit and alarm registration heals the alarm.
    await this.arm();
  }
  async alarm(): Promise<void> {
    // Each claim is durable before network I/O. Unknown delivery is never retried.
    for (let n = 0; n < 3; n++) {
      const item = this.ctx.storage.transactionSync(() => {
        const s = this.read(); if (!s) return null;
        const now = Date.now(); maintenance(s, now);
        s.outbox = s.outbox.filter(x => x.kind !== 'reminder' || s.alerts || x.status === 'dispatching');
        const found = s.outbox.find(x => x.status === 'pending' && x.due <= now);
        if (found) { found.status = 'dispatching'; found.claimed = now; }
        this.write(s); return found ? { ...found, chat: s.chat } : null;
      });
      await this.arm(); // Recovery alarm if the process ends during the fetch.
      if (!item) return;
      const result = await send(this.env.TELEGRAM_BOT_TOKEN, item.chat, item.text);
      this.ctx.storage.transactionSync(() => {
        const s = this.read(); if (!s) return;
        const current = s.outbox.find(x => x.id === item.id); if (!current) return;
        if (result.code === 429) {
          current.status = 'pending'; current.due = Date.now() + Math.max(1000, result.retry * 1000);
        } else if (result.code === 200 || result.code === 400 || result.code === 403) {
          s.outbox = s.outbox.filter(x => x.id !== item.id);
          if (result.code === 403) { s.alerts = false; s.reminders = []; s.outbox = s.outbox.filter(x => x.kind !== 'reminder'); }
        } else current.status = 'unknown';
        this.write(s);
      });
      await this.arm();
      if (result.code === 429) return;
    }
  }
}
async function send(token: string, chat: number, text: string): Promise<{ code: number; retry: number }> {
  if (!/^\d+:[A-Za-z0-9_-]{20,}$/.test(token ?? '')) return { code: 0, retry: 0 };
  try {
    const response = await fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(8000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text, protect_content: true, reply_markup: KEYBOARD, link_preview_options: { is_disabled: true } }),
    });
    const data: unknown = JSON.parse(await limitedText(response.body, 32_768));
    if (!record(data)) return { code: 0, retry: 0 };
    if (response.ok && data.ok === true) return { code: 200, retry: 0 };
    const code = Number(data.error_code), params = record(data.parameters) ? data.parameters : {};
    return { code, retry: Math.min(3600, Math.max(1, Number(params.retry_after) || 1)) };
  } catch { return { code: 0, retry: 0 }; }
}
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (request.method === 'GET' && (path === '/' || path === '/privacidad')) return reply(page(env, path === '/privacidad'), 200, 'text/html; charset=utf-8');
    if (request.method === 'GET' && path === '/health') return reply(JSON.stringify({ service: 'ruta-consular', version: '2.1.1', ready: configured(env) }), configured(env) ? 200 : 503, 'application/json');
    if (path !== '/telegram/webhook') return reply('Not found', 404);
    if (request.method !== 'POST') return reply('Method not allowed', 405);
    if (!configured(env)) return reply('Service not configured', 503);
    if (!await authorized(request, env.WEBHOOK_SECRET)) return reply('Forbidden', 403);
    if (!request.headers.get('Content-Type')?.toLowerCase().startsWith('application/json')) return reply('JSON required', 415);
    let update: unknown;
    try { update = JSON.parse(await limitedText(request.body)); } catch { return reply('Invalid or oversized payload', 400); }
    if (!privateUpdate(update)) return reply('OK');
    // No public route exposes the object, its state, or administrative RPCs.
    try {
      await env.CHATS.getByName('private:' + update.message.chat.id).accept(update);
      return reply('OK');
    } catch { console.error(JSON.stringify({ event: 'webhook_storage_failed' })); return reply('Temporary failure', 503); }
  },
} satisfies ExportedHandler<Env>;
