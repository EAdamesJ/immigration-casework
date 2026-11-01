// Pure command logic. Interview answers and raw Telegram updates are never stored.
export const DAY = 86_400_000;
export const KEYBOARD = { keyboard: [['/pendientes', '/entrevista'], ['/ds260', '/documentos'], ['/avisos', '/ayuda']], resize_keyboard: true };
export const PRIVACY = 'Ruta Consular es independiente: organiza tareas y práctica; no representa al Gobierno ni firma solicitudes. Telegram y el operador procesan mensajes. No envíes pasaportes, números de caso, datos médicos ni archivos. Guardo tareas breves, zona, preferencia de avisos e índice de práctica; no guardo respuestas de entrevista. /borrar confirmar elimina tus datos activos del bot; el historial de Telegram y las copias del proveedor se gestionan aparte. Los datos activos caducan tras 90 días sin uso.';
export const QUESTIONS = {
  b1b2: ['¿Cuál es el propósito concreto de su visita?', '¿Cuánto tiempo planea quedarse y por qué?', '¿Quién pagará y cómo se cubrirá el presupuesto?', '¿Qué planes y compromisos tiene al regresar?', '¿A qué se dedica actualmente?', '¿Qué viajes y estancias anteriores debe declarar?', '¿A quién visitará o dónde se alojará?', '¿Ha tenido negativas y qué circunstancias han cambiado?', '¿Existen peticiones migratorias y cuál es su situación?'],
  inmigrante: ['¿Qué categoría de visa solicita y quién presentó la petición, si corresponde?', '¿Qué datos del DS-260 debe confirmar con los documentos originales?', '¿Qué relación existe con el peticionario, si corresponde?', '¿Qué historial de domicilios, trabajo y estudios necesita aclarar?', '¿Qué viajes, negativas o antecedentes migratorios debe declarar con precisión?', '¿Qué documentos civiles le han solicitado y cuáles faltan?', '¿Qué plan de residencia y apoyo en Estados Unidos puede explicar con datos reales?', '¿Qué información necesita revisar con un profesional antes de responder?'],
};
export type Mode = keyof typeof QUESTIONS;
export interface Outgoing { id: string; text: string; kind: 'reply' | 'reminder'; due: number; created: number; status: 'pending' | 'dispatching' | 'unknown'; claimed?: number }
export interface State {
  chat: number; active: boolean; seen: number; window: number; count: number;
  zone: string | null; alerts: boolean; practice: { mode: Mode; index: number; skipped: number } | null;
  nextTask: number; tasks: { id: number; title: string }[];
  reminders: { due: number; title: string }[]; outbox: Outgoing[];
  lastDelivery?: { at: number; code: number; httpStatus: number; reason: string };
}
export interface Config { contact: string; privacy: string }
export function initial(chat: number, now: number): State {
  return { chat, active: true, seen: now, window: now, count: 0, zone: null, alerts: false, practice: null, nextTask: 1, tasks: [], reminders: [], outbox: [] };
}
export function queue(s: State, text: string, now: number, kind: Outgoing['kind'] = 'reply'): void {
  if (s.outbox.length < 60) s.outbox.push({ id: crypto.randomUUID(), text: text.slice(0, 3900), kind, due: now, created: now, status: 'pending' });
}
export function sensitive(text: string): boolean {
  return /\b(?:\d{3}-\d{2}-\d{4}|(?:IOE|EAC|WAC|LIN|SRC|MSC|NBC)\d{10}|A[- ]?\d{8,9})\b/i.test(text);
}
export function neutralTitle(text: string): boolean { return text.length > 0 && text.length <= 120 && !sensitive(text); }
export function validZone(zone: string): boolean {
  if (!zone || zone.length > 80) return false;
  try { new Intl.DateTimeFormat('en-US', { timeZone: zone }).format(); return true; } catch { return false; }
}
export function reminderTime(stamp: string, zone: string, now: number): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})([+-])(\d{2}):(\d{2})$/.exec(stamp);
  if (!m || Number(m[8]) > 23 || Number(m[9]) > 59 || !validZone(zone)) return null;
  const due = Date.parse(stamp);
  if (!Number.isFinite(due) || due <= now || due > now + 90 * DAY) return null;
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(due));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  const local = `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
  // Matching wall time also rejects invalid calendar dates and a wrong UTC offset.
  return local === stamp.slice(0, 19) ? due : null;
}
export function command(s: State, body: string, now: number, config: Config): string {
  const split = body.indexOf(' ');
  const cmd = (split < 0 ? body : body.slice(0, split)).split('@')[0].toLowerCase();
  const arg = split < 0 ? '' : body.slice(split + 1).trim();
  if (cmd === '/start' || cmd === '/ayuda') return PRIVACY + '\n\n/nuevo Revisar documento\n/pendientes\n/hecho 1\n/zona America/Santo_Domingo\n/avisos activar\n/recordar AAAA-MM-DDTHH:MM:SS-04:00 Revisar tarea\n/entrevista b1b2\n/entrevista inmigrante\n/siguiente\n/cancelar\n/ds260\n/documentos\n/privacidad\n/id\n/borrar\n\nPráctica guiada, sin IA generativa ni probabilidades de aprobación. Política: ' + config.privacy;
  if (cmd === '/privacidad') return PRIVACY + '\nContacto: ' + config.contact + '\nPolítica: ' + config.privacy;
  if (cmd === '/id') return 'Tu identificador privado es ' + s.chat + '. Esta versión Cloudflare no vincula expedientes privados; /pendientes muestra tus tareas de este bot.';
  if (cmd === '/borrar') {
    if (arg !== 'confirmar') return 'Usa /borrar confirmar para eliminar tareas, avisos y práctica de esta base activa. Telegram y copias del proveedor se gestionan aparte.';
    s.active = false; s.tasks = []; s.reminders = []; s.outbox = []; s.practice = null; s.zone = null; s.alerts = false;
    return 'Datos activos eliminados. Puedes volver a comenzar con /start. Esta confirmación conserva temporalmente el identificador necesario para enviarla.';
  }
  if (cmd === '/zona') {
    if (!validZone(arg)) return 'Usa /zona con un nombre IANA válido, por ejemplo America/Santo_Domingo o Europe/Madrid.';
    s.zone = arg; return 'Zona guardada. Usa el desplazamiento UTC correcto en cada recordatorio.';
  }
  if (cmd === '/avisos') {
    if (!['activar', 'desactivar'].includes(arg)) return 'Avisos ' + (s.alerts ? 'activados.' : 'desactivados.') + ' Usa /avisos activar o /avisos desactivar.';
    s.alerts = arg === 'activar';
    if (!s.alerts) { s.reminders = []; s.outbox = s.outbox.filter(x => x.kind !== 'reminder' || x.status === 'dispatching'); }
    return s.alerts ? 'Avisos activados para los recordatorios que programes.' : 'Avisos desactivados y recordatorios pendientes cancelados. Un envío ya iniciado puede completarse.';
  }
  if (cmd === '/nuevo') {
    if (!neutralTitle(arg)) return 'Usa /nuevo y un título genérico de hasta 120 caracteres, sin identificadores ni datos sensibles.';
    if (s.tasks.length >= 50) return 'Límite de 50 tareas. Completa algunas con /hecho.';
    const id = s.nextTask++; s.tasks.push({ id, title: arg }); return 'Tarea ' + id + ' guardada.';
  }
  if (cmd === '/hecho') {
    if (!/^\d{1,15}$/.test(arg) || !Number.isSafeInteger(Number(arg))) return 'Usa /hecho seguido del número de tu tarea.';
    const index = s.tasks.findIndex(x => x.id === Number(arg));
    if (index < 0) return 'No encontré esa tarea entre tus pendientes.';
    s.tasks.splice(index, 1); return 'Tarea completada.';
  }
  if (cmd === '/pendientes') return 'Tus pendientes del bot:\n' + (s.tasks.map(x => `${x.id}. ${x.title}`).join('\n') || 'Sin tareas.') + '\n\nRecordatorios programados: ' + s.reminders.length + '. No consulta USCIS ni expedientes externos.';
  if (cmd === '/recordar') {
    if (!s.zone || !s.alerts) return 'Primero configura /zona y activa /avisos activar. No hay avisos activos por defecto.';
    const at = arg.indexOf(' '), stamp = at < 0 ? arg : arg.slice(0, at), title = at < 0 ? '' : arg.slice(at + 1).trim();
    const due = reminderTime(stamp, s.zone, now);
    if (due === null || !neutralTitle(title)) return 'Usa /recordar AAAA-MM-DDTHH:MM:SS-04:00 Título genérico. Fecha futura dentro de 90 días y desplazamiento correcto para tu zona. No calculo plazos legales.';
    if (s.reminders.length >= 20) return 'Límite de 20 recordatorios. /avisos desactivar cancela los pendientes.';
    s.reminders.push({ due, title }); return 'Recordatorio guardado para ' + stamp + '. La entrega puede retrasarse; no reemplaza un plazo oficial.';
  }
  if (cmd === '/ds260') return 'Prepara identidad, pasaporte, domicilios, familia, empleo/estudios, viajes y antecedentes con documentos originales. No envíes respuestas sensibles aquí. Usa la hoja privada de la skill; revisa las preguntas reales en CEAC y firma personalmente. Guía oficial: https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/online-immigrant-visa-forms/ds-260-faqs.html';
  if (cmd === '/documentos') return 'La lista real depende del país, categoría e instrucciones oficiales. La skill privada prepara borradores, plantillas DOCX y PDF rellenables compatibles. No autentico ni certifico documentos; no descargo archivos aquí. https://github.com/EAdamesJ/immigration-casework';
  if (cmd === '/cancelar') { s.practice = null; return 'Práctica finalizada. No se guardaron tus respuestas en esta base.'; }
  if (cmd === '/entrevista') {
    if (arg !== 'b1b2' && arg !== 'inmigrante') return 'Elige /entrevista b1b2 o /entrevista inmigrante. Práctica orientativa, sin probabilidades de aprobación.';
    s.practice = { mode: arg, index: 0, skipped: 0 };
    return 'Práctica iniciada. Responde con tus hechos sin datos sensibles. No guardo tu respuesta; Telegram procesa el mensaje.\n\n' + QUESTIONS[arg][0];
  }
  if (s.practice && (!body.startsWith('/') || cmd === '/siguiente')) {
    const p = s.practice; p.index++;
    if (cmd === '/siguiente') p.skipped++;
    const feedback = cmd === '/siguiente' ? 'Pregunta omitida.' : 'Respuesta recibida sin verificar su exactitud. Comprueba su coherencia con tus documentos y reconoce lo que no recuerdes.';
    if (p.index >= QUESTIONS[p.mode].length) { s.practice = null; return feedback + '\nPráctica terminada. Preguntas omitidas: ' + p.skipped + '. Esto no decide elegibilidad ni aprobación.'; }
    return feedback + '\n\n' + QUESTIONS[p.mode][p.index];
  }
  return 'Usa /ayuda. Las respuestas libres solo avanzan una práctica activa; este bot básico no utiliza IA generativa ni sustituye a un abogado.';
}
export function maintenance(s: State, now: number): void {
  if (s.active && now - s.seen >= 90 * DAY) { s.active = false; s.tasks = []; s.reminders = []; s.outbox = []; s.practice = null; s.zone = null; s.alerts = false; }
  s.outbox = s.outbox.filter(x => now - x.created < 7 * DAY);
  for (const item of s.outbox) if (item.status === 'dispatching' && now - (item.claimed ?? 0) >= 120_000) item.status = 'unknown';
  const due = s.reminders.filter(x => x.due <= now);
  s.reminders = s.reminders.filter(x => x.due > now);
  if (s.active && s.alerts) for (const item of due) if (now - item.due <= DAY) queue(s, 'Recordatorio: ' + item.title, now, 'reminder');
}
export function nextAlarm(s: State, now: number): number | null {
  const times: number[] = [];
  if (s.active) times.push(s.seen + 90 * DAY);
  for (const r of s.reminders) times.push(r.due);
  for (const x of s.outbox) times.push(x.status === 'pending' ? x.due : x.status === 'dispatching' ? (x.claimed ?? now) + 120_000 : x.created + 7 * DAY);
  return times.length ? Math.max(now + 100, Math.min(...times)) : null;
}
