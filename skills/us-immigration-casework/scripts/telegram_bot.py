#!/usr/bin/env python3
"""Ruta Consular: optional public Telegram bot, private chats, local durable state."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4
from zoneinfo import ZoneInfo

from agenda import instant
from preparation import private_dir
from visitor import TOPICS

NAME='Ruta Consular'
COMMANDS=[('start','Abrir Ruta Consular'),('ayuda','Ver comandos y ejemplos'),('pendientes','Consultar mis tareas'),
          ('nuevo','Crear una tarea breve'),('hecho','Completar una tarea'),('zona','Configurar zona horaria'),
          ('avisos','Activar o desactivar recordatorios'),('recordar','Programar un recordatorio'),
          ('entrevista','Practicar B1B2 o visa de inmigrante'),('siguiente','Saltar la pregunta actual'),
          ('cancelar','Terminar la práctica'),('ds260','Preparar el DS260'),('documentos','Revisar tipos de documentos'),
          ('id','Ver mi identificador para vinculación'),('privacidad','Consultar datos y privacidad'),('borrar','Borrar mis datos del bot')]
KEYBOARD={'keyboard':[[{'text':'/pendientes'},{'text':'/entrevista'}],[{'text':'/ds260'},{'text':'/documentos'}],[{'text':'/avisos'},{'text':'/ayuda'}]],'resize_keyboard':True}
IMMIGRANT_QUESTIONS=['¿Qué categoría de visa de inmigrante solicita y quién presentó la petición, si corresponde?',
 '¿Qué datos de su DS-260 debe confirmar con los documentos originales?',
 '¿Qué relación existe con el peticionario, si la categoría se basa en una relación familiar?',
 '¿Qué historial de domicilios, trabajo y estudios necesita aclarar?',
 '¿Qué viajes, negativas o antecedentes migratorios debe declarar con precisión?',
 '¿Qué documentos civiles le han solicitado y cuáles faltan?',
 '¿Qué plan de residencia y apoyo en Estados Unidos puede explicar con sus datos reales?',
 '¿Qué información necesita revisar con un profesional antes de responder?']
DS260_URL='https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/online-immigrant-visa-forms/ds-260-faqs.html'
PRIVACY=('Este bot independiente organiza tareas y práctica; no representa al Gobierno ni firma solicitudes. '
 'Telegram y el operador procesan los mensajes: no envíes pasaportes, números de caso, datos médicos ni archivos. '
 'Guardo tareas breves, zona, preferencia de avisos e índice de práctica; no guardo tus respuestas de entrevista. '
 'Los avisos requieren /avisos activar. /borrar confirmar elimina tus datos de esta base; no elimina el historial de Telegram ni copias de seguridad. '
 'Inactividad de 90 días elimina los datos locales. El operador debe publicar su contacto y política completa antes de abrir el servicio.')


class ApiError(Exception):
    def __init__(self,code=0,retry_after=0):self.code=code;self.retry_after=retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class TelegramAPI:
    def __init__(self,token):
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token):raise ValueError('Invalid token format.')
        self._token=token;self._opener=urllib.request.build_opener(NoRedirect())

    def call(self,method,data=None,photo=None):
        if method not in {'getMe','getUpdates','getWebhookInfo','deleteWebhook','sendMessage','setMyCommands','getMyCommands','setChatMenuButton','getChatMenuButton','setMyName','setMyDescription','setMyShortDescription','setMyProfilePhoto','getUserProfilePhotos'}:
            raise ValueError('Unsupported Telegram method.')
        data=data or {};headers={}
        if photo is None:
            body=json.dumps(data).encode();headers['Content-Type']='application/json'
        else:
            file=Path(photo)
            if not file.is_file() or file.stat().st_size>10_000_000 or file.suffix.lower() not in {'.jpg','.jpeg'}:raise ValueError('Use a JPEG icon below 10 MB.')
            boundary='casework'+uuid4().hex;parts=[]
            for key,value in data.items():
                encoded=json.dumps(value) if not isinstance(value,str) else value
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{encoded}\r\n'.encode())
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo_file"; filename="icon.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+file.read_bytes()+b'\r\n')
            body=b''.join(parts)+f'--{boundary}--\r\n'.encode();headers['Content-Type']='multipart/form-data; boundary='+boundary
        request=urllib.request.Request('https://api.telegram.org/bot'+self._token+'/'+method,data=body,headers=headers,method='POST')
        try:
            with self._opener.open(request,timeout=40) as response:raw=response.read(5_000_001)
            if len(raw)>5_000_000:raise ApiError()
            result=json.loads(raw)
        except urllib.error.HTTPError as error:
            try:
                result=json.loads(error.read(10000))
                raise ApiError(int(result.get('error_code',error.code)),min(300,max(0,int(result.get('parameters',{}).get('retry_after',0))))) from None
            except (ValueError,TypeError):raise ApiError(error.code) from None
        except (OSError,ValueError,urllib.error.URLError):raise ApiError() from None
        if not isinstance(result,dict):raise ApiError()
        if result.get('ok') is not True:raise ApiError(int(result.get('error_code',0)))
        return result.get('result')


def token_from_environment():
    location=os.environ.get('TELEGRAM_BOT_TOKEN_FILE')
    token=Path(location).read_text().strip() if location else os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    if not token:raise ValueError('Configure TELEGRAM_BOT_TOKEN_FILE or TELEGRAM_BOT_TOKEN securely.')
    return token


def configure(api,photo=None):
    identity=api.call('getMe')
    api.call('setMyName',{'name':NAME})
    api.call('setMyDescription',{'description':'Organiza pendientes, recibe recordatorios y practica entrevistas consulares. Preparación independiente de DS-160, DS-260 y documentos; no firma ni presenta solicitudes.'})
    api.call('setMyShortDescription',{'short_description':'Tareas, avisos y práctica consular. Asistente independiente; sin garantías de aprobación.'})
    commands=[{'command':cmd,'description':description} for cmd,description in COMMANDS]
    api.call('setMyCommands',{'commands':commands})
    api.call('setMyCommands',{'commands':commands,'scope':{'type':'all_private_chats'}})
    api.call('setChatMenuButton',{'menu_button':{'type':'commands'}})
    if photo:api.call('setMyProfilePhoto',{'photo':{'type':'static','photo':'attach://photo_file'}},photo=photo)
    return {'status':'configured','username':identity.get('username'),'commands':len(commands)}


def verify_profile(api):
    identity=api.call('getMe');expected=[{'command':cmd,'description':description} for cmd,description in COMMANDS]
    default=api.call('getMyCommands');private=api.call('getMyCommands',{'scope':{'type':'all_private_chats'}})
    menu=api.call('getChatMenuButton');photos=api.call('getUserProfilePhotos',{'user_id':identity['id'],'limit':1})
    matched=default==expected and private==expected and menu.get('type')=='commands' and identity.get('first_name')==NAME
    return {'status':'profile_verified' if matched else 'profile_mismatch','username':identity.get('username'),
            'commands_match':matched,'photo_present':photos.get('total_count',0)>0,'worker_running_proven':False}


class BotStore:
    def __init__(self,path,max_users=10000):
        path=Path(path).expanduser().absolute()
        if any(p.is_symlink() for p in (path,*path.parents)) or any((p/'.git').exists() for p in path.parents):raise ValueError('Use a private path outside Git and symlinks.')
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=10);self.db.execute('PRAGMA foreign_keys=ON');self.max_users=max_users
        self.db.executescript('''CREATE TABLE IF NOT EXISTS users(chat INTEGER PRIMARY KEY, zone TEXT, alerts INTEGER DEFAULT 0, practice TEXT, seen INTEGER, window INTEGER DEFAULT 0, count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, chat INTEGER REFERENCES users ON DELETE CASCADE, title TEXT);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, chat INTEGER REFERENCES users ON DELETE CASCADE, due INTEGER, title TEXT);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, chat INTEGER, body TEXT, kind TEXT, status TEXT DEFAULT 'pending', due INTEGER, created INTEGER);
        CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY, seen INTEGER);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS bindings(chat INTEGER PRIMARY KEY REFERENCES users ON DELETE CASCADE, ledger TEXT, case_id TEXT, actor TEXT, verification_ref TEXT);''')
        self.db.commit()
        if os.name=='posix':path.chmod(0o600)

    def close(self):self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:yield;self.db.commit()
        except Exception:self.db.rollback();raise

    def offset(self):
        row=self.db.execute("SELECT value FROM meta WHERE key='offset'").fetchone();return int(row[0]) if row else 0

    def enqueue(self,chat,body,now,kind='reply'):
        self.db.execute('INSERT INTO outbox(chat,body,kind,due,created) VALUES(?,?,?,?,?)',(chat,body[:3900],kind,now,now))

    def handle(self,update,now):
        if not isinstance(update,dict) or type(update.get('update_id')) is not int:return
        update_id=update['update_id']
        with self.transaction():
            if self.db.execute('SELECT 1 FROM updates WHERE id=?',(update_id,)).fetchone():return
            self.db.execute('INSERT INTO updates VALUES(?,?)',(update_id,now))
            self.db.execute("INSERT INTO meta VALUES('offset',?) ON CONFLICT(key) DO UPDATE SET value=MAX(CAST(value AS INTEGER),CAST(excluded.value AS INTEGER))",(str(update_id+1),))
            message=update.get('message',{});chat=message.get('chat',{});sender=message.get('from',{})
            if chat.get('type')!='private' or type(chat.get('id')) is not int or chat['id']<=0 or type(sender.get('id')) is not int or sender['id']!=chat['id'] or sender.get('is_bot') is True:return
            chat_id=chat['id'];body=message.get('text','')
            if not isinstance(body,str):return
            user=self.db.execute('SELECT zone,alerts,practice,window,count FROM users WHERE chat=?',(chat_id,)).fetchone()
            if user is None:
                if not body.startswith('/start'):return
                if self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]>=self.max_users:return
                self.db.execute('INSERT INTO users(chat,seen) VALUES(?,?)',(chat_id,now));user=(None,0,None,0,0)
            window,count=user[3],user[4]
            if now-window>=60:window,count=now,0
            if count>=15 and body.strip()!='/borrar confirmar':return
            self.db.execute('UPDATE users SET seen=?,window=?,count=? WHERE chat=?',(now,window,count+1,chat_id))
            if message.get('document') or message.get('photo') or message.get('voice'):
                self.enqueue(chat_id,'No descargo archivos aquí. Trabaja los documentos sensibles en el expediente privado de la skill. Usa /documentos.',now);return
            if len(body)>4000:self.enqueue(chat_id,'Usa mensajes breves y no incluyas datos sensibles.',now);return
            reply=self.command(chat_id,body.strip(),now,user)
            self.enqueue(chat_id,reply,now)

    def command(self,chat,body,now,user):
        first,_,argument=body.partition(' ');cmd=first.split('@',1)[0].lower();argument=argument.strip()
        if cmd in {'/start','/ayuda'}:
            return NAME+'\n'+PRIVACY+'\n\n/nuevo Revisar documento\n/pendientes\n/hecho 1\n/zona America/Santo_Domingo\n/avisos activar\n/recordar 2027-01-12T09:00:00-04:00 Revisar tarea\n/entrevista b1b2\n/entrevista inmigrante\n/ds260\n/documentos\n\nEl bot básico no utiliza IA generativa ni decide elegibilidad.'
        if cmd=='/privacidad':return PRIVACY+'\nContacto del operador: '+os.environ.get('BOT_OPERATOR_CONTACT','[pendiente]')+'\nPolítica completa: '+os.environ.get('BOT_PRIVACY_URL','[pendiente]')
        if cmd=='/id':return 'Tu identificador privado es '+str(chat)+'. Solo un operador que verifique tu autoridad puede vincularte a un expediente. Nunca publiques el identificador junto con documentos.'
        if cmd=='/borrar':
            if argument!='confirmar':return 'Para borrar tareas, avisos, práctica y vínculo de esta base usa /borrar confirmar. El historial de Telegram y las copias de seguridad se gestionan aparte.'
            self.db.execute('DELETE FROM outbox WHERE chat=?',(chat,));self.db.execute('DELETE FROM users WHERE chat=?',(chat,));return 'Datos locales eliminados. Puedes volver a comenzar con /start.'
        if cmd=='/zona':
            try:ZoneInfo(argument)
            except (ValueError,KeyError):return 'Usa /zona con un nombre IANA válido, por ejemplo America/Santo_Domingo o Europe/Madrid.'
            self.db.execute('UPDATE users SET zone=? WHERE chat=?',(argument,chat));return 'Zona guardada. Los recordatorios requieren fecha y hora con el desplazamiento UTC correcto.'
        if cmd=='/avisos':
            if argument not in {'activar','desactivar'}:return 'Avisos '+('activados.' if user[1] else 'desactivados.')+' Usa /avisos activar o /avisos desactivar. Un aviso es un recordatorio personal, no vigilancia de trámites.'
            active=argument=='activar';self.db.execute('UPDATE users SET alerts=? WHERE chat=?',(int(active),chat))
            if not active:
                self.db.execute('DELETE FROM reminders WHERE chat=?',(chat,));self.db.execute("DELETE FROM outbox WHERE chat=? AND kind='reminder' AND status='pending'",(chat,))
            return 'Avisos activados para los recordatorios que programes.' if active else 'Avisos desactivados y recordatorios pendientes cancelados. Un envío que ya comenzó puede no poder retirarse.'
        if cmd=='/nuevo':
            if not 1<=len(argument)<=120 or self.sensitive(argument):return 'Usa /nuevo y un título genérico de hasta 120 caracteres, sin identificadores ni datos sensibles.'
            if self.db.execute('SELECT COUNT(*) FROM tasks WHERE chat=?',(chat,)).fetchone()[0]>=50:return 'Límite de 50 tareas. Completa algunas con /hecho.'
            cursor=self.db.execute('INSERT INTO tasks(chat,title) VALUES(?,?)',(chat,argument));return 'Tarea '+str(cursor.lastrowid)+' guardada.'
        if cmd=='/hecho':
            if not argument.isdigit() or len(argument)>18:return 'Usa /hecho seguido del número de tu tarea.'
            cursor=self.db.execute('DELETE FROM tasks WHERE id=? AND chat=?',(int(argument),chat));return 'Tarea completada.' if cursor.rowcount else 'No encontré esa tarea entre tus pendientes.'
        if cmd=='/pendientes':return self.pending(chat)
        if cmd=='/recordar':
            if not user[0] or not user[1]:return 'Primero configura /zona y activa /avisos activar. No hay avisos activos por defecto.'
            stamp,_,title=argument.partition(' ')
            try:
                point=instant(stamp);local=point.astimezone(ZoneInfo(user[0]));due=int(point.timestamp())
                if local.replace(tzinfo=None)!=point.replace(tzinfo=None) or local.utcoffset()!=point.utcoffset():raise ValueError()
                if not now<due<=now+90*86400 or not 1<=len(title.strip())<=120 or self.sensitive(title):raise ValueError()
            except (ValueError,KeyError,OverflowError):return 'Usa /recordar AAAA-MM-DDTHH:MM:SS-04:00 Título genérico. Confirma el desplazamiento de tu zona; fecha futura dentro de 90 días. No calculo plazos legales.'
            if self.db.execute('SELECT COUNT(*) FROM reminders WHERE chat=?',(chat,)).fetchone()[0]>=20:return 'Límite de 20 recordatorios. /avisos desactivar permite cancelarlos.'
            self.db.execute('INSERT INTO reminders(chat,due,title) VALUES(?,?,?)',(chat,due,title.strip()));return 'Recordatorio guardado para '+stamp+'. El servicio debe estar funcionando; no garantiza entrega ni reemplaza un plazo oficial.'
        if cmd=='/ds260':return 'DS-260: prepara identidad, pasaporte, domicilios, familia, empleo/estudios, viajes y antecedentes con documentos originales. No envíes números ni respuestas sensibles aquí. La skill incluye hoja privada, revisión y exportación; el solicitante revisa cada pregunta del CEAC y firma. Guía oficial: '+DS260_URL
        if cmd=='/documentos':return 'Puedo orientar sobre pasaporte, actas, matrimonio/divorcio, antecedentes cuando correspondan, documentos financieros y cartas; la lista real depende del país, categoría e instrucciones vigentes. La skill trabaja borradores, DOCX y PDF rellenables con plantilla. No autentico ni certifico documentos y no descargo archivos aquí.'
        if cmd=='/cancelar':self.db.execute('UPDATE users SET practice=NULL WHERE chat=?',(chat,));return 'Práctica finalizada. No se guardaron tus respuestas en esta base.'
        if cmd=='/entrevista':
            if argument not in {'b1b2','inmigrante'}:return 'Elige /entrevista b1b2 o /entrevista inmigrante. Práctica orientativa, sin probabilidades de aprobación; evita datos sensibles.'
            practice={'mode':argument,'index':0,'skipped':0};self.db.execute('UPDATE users SET practice=? WHERE chat=?',(json.dumps(practice),chat))
            return 'Práctica iniciada. Responde con tus hechos, sin números ni datos sensibles. No guardo la respuesta; Telegram sí procesa el mensaje.\n\n'+self.questions(argument)[0]
        if user[2] and (not body.startswith('/') or cmd=='/siguiente'):
            practice=json.loads(user[2]);questions=self.questions(practice['mode']);practice['index']+=1
            if cmd=='/siguiente':practice['skipped']+=1;feedback='Pregunta omitida; queda pendiente.'
            else:feedback='Respuesta recibida, sin verificar su exactitud. '+('Procura una explicación breve y directa.' if len(body)>700 else 'Comprueba que coincida con tus documentos y reconoce lo que no recuerdes.')
            if practice['index']>=len(questions):
                self.db.execute('UPDATE users SET practice=NULL WHERE chat=?',(chat,));return feedback+'\nPráctica terminada; preguntas omitidas: '+str(practice['skipped'])+'. Esto no determina elegibilidad ni aprobación.'
            self.db.execute('UPDATE users SET practice=? WHERE chat=?',(json.dumps(practice),chat));return feedback+'\n\n'+questions[practice['index']]
        return 'Usa /ayuda para ver las opciones. No soy un abogado ni un chat de asesoría generativa; las respuestas libres solo avanzan una práctica activa.'

    @staticmethod
    def sensitive(value):
        return bool(re.search(r'\b(?:\d{3}-\d{2}-\d{4}|(?:IOE|EAC|WAC|LIN|SRC|MSC|NBC)\d{10}|A[- ]?\d{8,9})\b',value,re.I))

    @staticmethod
    def questions(mode):return [q[0] for q in TOPICS.values()] if mode=='b1b2' else IMMIGRANT_QUESTIONS

    def pending(self,chat):
        rows=self.db.execute('SELECT id,title FROM tasks WHERE chat=? ORDER BY id LIMIT 50',(chat,)).fetchall()
        output='Tus pendientes locales:\n'+('\n'.join(str(i)+'. '+title for i,title in rows) if rows else 'Sin tareas.')
        binding=self.db.execute('SELECT ledger,case_id,actor FROM bindings WHERE chat=?',(chat,)).fetchone()
        if binding:
            from coordination import Store
            ledger=None
            try:
                ledger=Store(binding[0]);case=ledger.snapshot()[1]['cases'][binding[1]];role=case['members'][binding[2]]
                tasks=[(key,task) for key,task in case['tasks'].items() if task['status']!='done' and (role=='owner' or task['assignee']==binding[2])]
                output+='\n\nExpediente vinculado (solo lectura, títulos reservados al expediente):\n'+'\n'.join(binding[1]+' / '+key+' ['+task['status']+']' for key,task in tasks[:15])
            except (OSError,ValueError,KeyError,sqlite3.Error):output+='\nVínculo no disponible; requiere revisión del operador.'
            finally:
                if ledger:ledger.close()
        return output[:3800]

    def link(self,chat,ledger,case_id,actor,verification_ref):
        from coordination import Store
        from preparation import identifier
        identifier(case_id);identifier(actor);identifier(verification_ref);store=Store(ledger)
        try:
            if actor not in store.snapshot()[1]['cases'][case_id]['members']:raise ValueError('Actor is not a case member.')
        finally:store.close()
        with self.transaction():
            if not self.db.execute('SELECT 1 FROM users WHERE chat=?',(chat,)).fetchone():raise ValueError('Private user must start the bot first.')
            self.db.execute('INSERT INTO bindings VALUES(?,?,?,?,?) ON CONFLICT(chat) DO UPDATE SET ledger=excluded.ledger,case_id=excluded.case_id,actor=excluded.actor,verification_ref=excluded.verification_ref',(chat,str(Path(ledger).resolve()),case_id,actor,verification_ref))

    def tick(self,now):
        with self.transaction():
            for row in self.db.execute('SELECT r.id,r.chat,r.due,r.title FROM reminders r JOIN users u ON u.chat=r.chat WHERE r.due<=? AND u.alerts=1 LIMIT 100',(now,)).fetchall():
                if now-row[2]<=86400:self.enqueue(row[1],'Recordatorio: '+row[3],now,'reminder')
                self.db.execute('DELETE FROM reminders WHERE id=?',(row[0],))
            stale=[row[0] for row in self.db.execute('SELECT chat FROM users WHERE seen<?',(now-90*86400,)).fetchall()]
            for chat in stale:self.db.execute('DELETE FROM outbox WHERE chat=?',(chat,));self.db.execute('DELETE FROM users WHERE chat=?',(chat,))
            self.db.execute('DELETE FROM updates WHERE seen<?',(now-7*86400,));self.db.execute('DELETE FROM outbox WHERE created<?',(now-7*86400,))

    def flush_one(self,api,now):
        with self.transaction():
            row=self.db.execute("SELECT id,chat,body,kind FROM outbox WHERE status='pending' AND due<=? ORDER BY id LIMIT 1",(now,)).fetchone()
            if row is None:return False
            if row[3]=='reminder' and not self.db.execute('SELECT 1 FROM users WHERE chat=? AND alerts=1',(row[1],)).fetchone():
                self.db.execute('DELETE FROM outbox WHERE id=?',(row[0],));return True
            self.db.execute("UPDATE outbox SET status='dispatching' WHERE id=?",(row[0],))
        try:
            api.call('sendMessage',{'chat_id':row[1],'text':row[2],'protect_content':True,'reply_markup':KEYBOARD,'link_preview_options':{'is_disabled':True}})
        except ApiError as error:
            with self.transaction():
                if error.code==429:self.db.execute("UPDATE outbox SET status='pending',due=? WHERE id=?",(now+max(1,error.retry_after),row[0]))
                elif error.code in {400,403}:
                    self.db.execute('DELETE FROM outbox WHERE id=?',(row[0],))
                    if error.code==403:self.db.execute('UPDATE users SET alerts=0 WHERE chat=?',(row[1],))
                else:self.db.execute("UPDATE outbox SET status='unknown' WHERE id=?",(row[0],))
        else:
            with self.transaction():self.db.execute('DELETE FROM outbox WHERE id=?',(row[0],))
        return True


def serve(store,api):
    if api.call('getWebhookInfo').get('url'):raise ValueError('A webhook is configured; remove it explicitly before polling.')
    store.db.execute("UPDATE outbox SET status='unknown' WHERE status='dispatching'");store.db.commit()
    running=True
    def stop(*_):
        nonlocal running;running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    while running:
        try:
            backlog=store.db.execute("SELECT 1 FROM outbox WHERE status='pending' AND due<=? LIMIT 1",(int(time.time()),)).fetchone()
            for update in api.call('getUpdates',{'offset':store.offset(),'limit':50,'timeout':1 if backlog else 10,'allowed_updates':['message']}):store.handle(update,int(time.time()))
            store.tick(int(time.time()))
            for _ in range(20):
                if not store.flush_one(api,int(time.time())):break
                time.sleep(.1)
        except ApiError as error:time.sleep(max(1,error.retry_after) if error.code==429 else 5)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    setup=sub.add_parser('setup');setup.add_argument('--photo')
    sub.add_parser('verify')
    run=sub.add_parser('run');run.add_argument('--db',required=True);run.add_argument('--max-users',type=int,default=10000)
    status=sub.add_parser('status');status.add_argument('--db',required=True)
    link=sub.add_parser('link');link.add_argument('--db',required=True);link.add_argument('--chat-id',required=True,type=int)
    for name in ('ledger','case-id','actor','verification-ref'):link.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);store=None
    try:
        if args.command=='setup':result=configure(TelegramAPI(token_from_environment()),args.photo)
        elif args.command=='verify':result=verify_profile(TelegramAPI(token_from_environment()))
        elif args.command=='run':
            if not 1<=args.max_users<=100000:raise ValueError('Invalid capacity.')
            contact=os.environ.get('BOT_OPERATOR_CONTACT','').strip();policy=os.environ.get('BOT_PRIVACY_URL','')
            if not contact or contact.startswith('REPLACE_') or not policy.startswith('https://'):
                raise ValueError('Configure real operator contact and a public HTTPS privacy policy before opening the service.')
            store=BotStore(args.db,args.max_users);serve(store,TelegramAPI(token_from_environment()));return 0
        elif args.command=='status':
            if not Path(args.db).is_file():raise ValueError('Existing database required.')
            store=BotStore(args.db);result={'users':store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                                         'pending_messages':store.db.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0],
                                         'unknown_messages':store.db.execute("SELECT COUNT(*) FROM outbox WHERE status='unknown'").fetchone()[0]}
        else:
            store=BotStore(args.db);store.link(args.chat_id,args.ledger,args.case_id,args.actor,args.verification_ref);result={'status':'linked_read_only'}
        print(json.dumps(result));return 0
    except (OSError,ValueError,KeyError,sqlite3.Error,ApiError):
        print('Telegram operation failed. Check local configuration, API permissions, token and service state. Secrets and message contents are omitted.',file=sys.stderr);return 2
    finally:
        if store:store.close()


if __name__=='__main__':raise SystemExit(main())
