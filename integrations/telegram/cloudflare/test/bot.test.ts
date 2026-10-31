import { describe, it, expect } from 'vitest';
import { command, DAY, initial, maintenance, nextAlarm, queue, reminderTime, type State } from '../src/bot';
const now = Date.parse('2026-10-31T12:00:00Z');
const config = { contact: 'Test operator', privacy: 'https://example.org/privacy' };
function run(s: State, text: string) { return command(s, text, now, config); }
describe('Commands and preparation boundaries', () => {
  it('requires opt-in and timezone for reminders', () => {
    const s = initial(1, now); expect(run(s, '/recordar 2026-11-01T09:00:00-04:00 Revisar')).toContain('Primero');
    run(s, '/avisos activar'); expect(run(s, '/recordar 2026-11-01T09:00:00-04:00 Revisar')).toContain('Primero');
    run(s, '/zona America/Santo_Domingo'); expect(run(s, '/recordar 2026-11-01T09:00:00-04:00 Revisar')).toContain('guardado'); expect(s.reminders).toHaveLength(1);
  });
  it('rejects incorrect offsets, calendar dates and missing offsets', () => {
    expect(reminderTime('2026-11-01T09:00:00-05:00', 'America/Santo_Domingo', now)).toBeNull();
    expect(reminderTime('2027-02-30T09:00:00-04:00', 'America/Santo_Domingo', now)).toBeNull();
    expect(reminderTime('2026-11-01T09:00:00', 'America/Santo_Domingo', now)).toBeNull();
  });
  it('checks DST for the actual date', () => {
    expect(reminderTime('2026-11-02T09:00:00-04:00', 'America/New_York', now)).toBeNull();
    expect(reminderTime('2026-11-02T09:00:00-05:00', 'America/New_York', now)).not.toBeNull();
  });
  it('rejects past and more than 90 days ahead', () => {
    expect(reminderTime('2026-10-30T09:00:00-04:00', 'America/Santo_Domingo', now)).toBeNull();
    expect(reminderTime('2027-03-01T09:00:00-04:00', 'America/Santo_Domingo', now)).toBeNull();
  });
  it('blocks selected identifiers and caps task titles', () => {
    const s = initial(1, now); run(s, '/nuevo IOE' + '1234567890'); run(s, '/nuevo ' + 'x'.repeat(121)); expect(s.tasks).toHaveLength(0);
  });
  it('caps tasks and reminder counts', () => {
    const s = initial(1, now); for (let i = 0; i < 51; i++) run(s, '/nuevo Revisar'); expect(s.tasks).toHaveLength(50);
    run(s, '/zona America/Santo_Domingo'); run(s, '/avisos activar'); for (let i = 0; i < 21; i++) run(s, '/recordar 2026-11-01T09:00:00-04:00 Revisar'); expect(s.reminders).toHaveLength(20);
  });
  it('cannot complete a nonexistent or unsafe task id', () => {
    const s = initial(1, now); run(s, '/nuevo Revisar'); expect(run(s, '/hecho 99')).toContain('No encontré'); expect(run(s, '/hecho ' + '9'.repeat(1000))).toContain('Usa /hecho'); expect(s.tasks).toHaveLength(1);
  });
  it('does not persist interview answers', () => {
    const s = initial(1, now); run(s, '/entrevista b1b2'); run(s, 'PRIVATE ANSWER SHOULD NEVER BE SAVED'); expect(JSON.stringify(s)).not.toContain('PRIVATE'); expect(s.practice?.index).toBe(1);
  });
  it('counts skipped questions and finishes practice', () => {
    const s = initial(1, now); run(s, '/entrevista inmigrante'); let result = ''; for (let i = 0; i < 8; i++) result = run(s, '/siguiente'); expect(s.practice).toBeNull(); expect(result).toContain('omitidas: 8');
  });
  it('cancels practice and keeps DS260 private', () => {
    const s = initial(1, now); run(s, '/entrevista b1b2'); run(s, '/cancelar'); expect(s.practice).toBeNull(); expect(run(s, '/ds260')).toContain('No envíes'); expect(run(s, '/documentos')).toContain('no descargo');
  });
  it('opt-out cancels future and queued reminders', () => {
    const s = initial(1, now); s.alerts = true; s.reminders.push({ due: now + 1000, title: 'Revisar' }); queue(s, 'reminder', now, 'reminder'); run(s, '/avisos desactivar'); expect(s.reminders).toHaveLength(0); expect(s.outbox).toHaveLength(0);
  });
  it('deletion clears tasks, preferences, practice and old outbox', () => {
    const s = initial(1, now); run(s, '/nuevo Revisar'); run(s, '/entrevista b1b2'); queue(s, 'old', now); run(s, '/borrar confirmar'); expect(s.active).toBe(false); expect(s.tasks).toHaveLength(0); expect(s.outbox).toHaveLength(0); expect(s.practice).toBeNull();
  });
  it('reminders require current consent and stale ones are dropped', () => {
    const s = initial(1, now); s.alerts = true; s.reminders = [{ due: now - 2 * DAY, title: 'stale' }, { due: now - 100, title: 'fresh' }]; maintenance(s, now); expect(s.outbox.map(x => x.text)).toEqual(['Recordatorio: fresh']);
  });
  it('expires inactive data and unknown deliveries', () => {
    const s = initial(1, now); run(s, '/nuevo Revisar'); queue(s, 'uncertain', now); s.outbox[0].status = 'unknown'; maintenance(s, now + 8 * DAY); expect(s.outbox).toHaveLength(0); maintenance(s, now + 90 * DAY); expect(s.active).toBe(false); expect(s.tasks).toHaveLength(0);
  });
  it('does not retry an expired in-flight claim', () => {
    const s = initial(1, now); queue(s, 'uncertain', now); s.outbox[0].status = 'dispatching'; s.outbox[0].claimed = now; maintenance(s, now + 120_000); expect(s.outbox[0].status).toBe('unknown'); expect(nextAlarm(s, now + 120_000)).toBe(now + 7 * DAY);
  });
});
