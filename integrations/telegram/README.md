# Ruta Consular en Telegram

Bot público de organización y práctica consular. Cualquier persona puede usarlo en un chat privado; cada usuario ve sus propias tareas. No es un chat de asesoría generativa, no descarga expedientes y no completa ni envía el DS-260 dentro de Telegram. El trabajo documental real se realiza con la skill en un espacio privado.

## Qué queda preparado

Nombre: **Ruta Consular**. Usuario sugerido: `RutaConsularBot`, sujeto a disponibilidad en BotFather; si no está libre, elige un sufijo propio como `RutaConsularEAdamesBot`. El nombre puede configurarse con el comando setup. El menú y el icono se registran en el bot que corresponda al token configurado, no en una cuenta supuesta por el código.

- [Icono JPEG listo para Telegram](ruta-consular.jpg)
- [Original PNG](ruta-consular.png)
- [Menú para BotFather](commands.txt)
- [Plantilla de privacidad que debes completar](PRIVACY.template.md)

## Crear o reutilizar el bot

1. Abre el **@BotFather oficial** en Telegram. Si ya tienes un bot, reutilízalo; no necesitas crear otro. Para uno nuevo, usa `/newbot`, indica Ruta Consular y elige un usuario disponible terminado en `bot`.
2. Guarda el token que decidas utilizar como secreto del servidor. Para cambiarlo en otro momento, BotFather ofrece `/revoke`; el programa no lo rota ni exige cambiarlo. No incluyas el token en comandos de ejemplo, GitHub ni registros. BotFather y sus ajustes son responsabilidad del propietario.
3. Para esta implementación, desactiva que se añada a grupos con `/setjoingroups`; mantén el modo de privacidad de grupos activado y no habilites el modo inline. La privacidad de grupos no cifra los chats privados del bot. El código ignora grupos, canales y remitentes que no coinciden con el chat privado.
4. Publica una política de privacidad real y un contacto del operador. La plantilla incluida debe completarse, reflejar el alojamiento y las copias de seguridad reales y revisarse para tus usuarios/jurisdicción. No es una política lista para afirmar cumplimiento.

## Ejecutar el servicio con Docker Compose

Necesitas Docker Engine/Compose en un equipo o servidor que permanezca encendido y acceso HTTPS saliente a `api.telegram.org`. No necesitas dominio, webhook ni puertos públicos para long polling. El número de usuarios permitido no es una prueba de carga ni una garantía de capacidad. Empieza con usuarios de prueba, monitoriza recursos y mantén **un solo worker** por token/base.

Desde la raíz de este repositorio, crea un archivo de configuración fuera de Git. En Linux/macOS:

```bash
umask 077
mkdir -p "$HOME/.config/ruta-consular"
cp integrations/telegram/.env.example "$HOME/.config/ruta-consular/bot.env"
chmod 600 "$HOME/.config/ruta-consular/bot.env"
```

Abre ese archivo con tu editor local y completa **solo allí**:

```dotenv
TELEGRAM_BOT_TOKEN=CONFIGURE_LOCALLY_FROM_BOTFATHER
BOT_OPERATOR_CONTACT=REPLACE_WITH_REAL_OPERATOR_CONTACT
BOT_PRIVACY_URL=REPLACE_WITH_PUBLIC_HTTPS_PRIVACY_POLICY
```

No imprimas el archivo ni ejecutes comandos que vuelquen el entorno. El proceso también admite `TELEGRAM_BOT_TOKEN_FILE` cuando tu plataforma ofrece un archivo secreto; no configures ambos mecanismos. El token nunca se guarda en SQLite.

Construye y configura nombre, descripción, comandos, menú e icono. **setup modifica el perfil real del bot cuyo token hayas guardado**; comprueba la cuenta antes de ejecutarlo:

```bash
export RUTA_ENV_FILE="$HOME/.config/ruta-consular/bot.env"
docker compose -f integrations/telegram/compose.yml build
docker compose -f integrations/telegram/compose.yml run --rm bot python scripts/telegram_bot.py setup --photo /app/ruta-consular.jpg
docker compose -f integrations/telegram/compose.yml run --rm bot python scripts/telegram_bot.py verify
docker compose -f integrations/telegram/compose.yml up -d
```

El resultado de setup informa el usuario real devuelto por Telegram. Usa ese usuario para compartir el enlace del bot después de la prueba; el nombre sugerido no demuestra que exista o te pertenezca. Si falla la foto por incompatibilidad del servidor, configura el menú sin `--photo` y usa `/setuserpic` en BotFather con el JPEG. No supongas que un setup parcial no hizo cambios: comprueba nombre y comandos antes de repetir.

La base persiste en un volumen local de Docker; no uses `down -v` salvo que quieras borrar ese volumen. El contenedor usa un usuario sin privilegios, sistema de archivos de aplicación de solo lectura y permisos reducidos. No hemos ejecutado Docker en el entorno de desarrollo de esta entrega: valida la construcción en tu host. El cifrado del disco, acceso a Docker, copias y política de retención deben configurarse allí. No publiques el archivo de entorno, el volumen ni una copia de SQLite.

Para consultar métricas sin mostrar usuarios ni mensajes:

```bash
docker compose -f integrations/telegram/compose.yml exec bot python scripts/telegram_bot.py status --db /data/telegram.sqlite3
```

Para parar el servicio usa `docker compose -f integrations/telegram/compose.yml stop`. Si el bot tenía un webhook, este worker se negará a iniciar: cambia la integración deliberadamente antes de habilitar polling; no borra webhooks por sí solo.

## Comandos y prueba pública

El archivo commands.txt se puede pegar en `/setcommands` como alternativa a setup. El menú incluye:

| Comando | Uso |
| --- | --- |
| /start /ayuda | Abrir el menú y conocer límites y ejemplos |
| /nuevo Revisar acta | Crear una tarea con título genérico |
| /pendientes | Ver tareas propias y estados de un expediente vinculado, si existe |
| /hecho 1 | Completar únicamente una tarea propia |
| /zona America/Santo_Domingo | Elegir zona IANA |
| /avisos activar | Consentir recordatorios personales |
| /avisos desactivar | Cancelar recordatorios pendientes |
| /recordar 2027-01-12T09:00:00-04:00 Revisar tarea | Fecha/hora futura, con offset correcto, dentro de 90 días |
| /entrevista b1b2 | Práctica guiada B1/B2, una pregunta por turno |
| /entrevista inmigrante | Práctica de visa de inmigrante |
| /siguiente /cancelar | Omitir pregunta o terminar práctica |
| /ds260 /documentos | Guía y acceso al flujo privado de preparación |
| /id | Identificador para vinculación verificada por un operador |
| /privacidad | Datos, retención y contacto |
| /borrar confirmar | Eliminar tareas, avisos, práctica y vínculo de la base activa |

Haz la prueba con **dos cuentas distintas**: cada una debe ver solo sus tareas, no poder completar las ajenas, consentir sus propios avisos y borrar sus datos. Usa datos inventados, programa un aviso cercano con la zona correcta y confirma su llegada. Comprueba reinicio, persistencia y respuesta al bloqueo del bot. Publica el enlace a cualquier usuario solo después de verificar esas pruebas y la política real.

El worker no guarda respuestas de entrevista en su base; Telegram sí procesa los mensajes. No descargues documentos ni envíes información sensible. Las heurísticas de identificadores no garantizan anonimización. El bot básico no usa ni necesita una API de IA. El servicio no garantiza entrega ni calcula plazos legales. Los resultados de envío inciertos se retienen sin reintento automático; las respuestas confirmadas se retiran de la cola. Un 429 de Telegram se reintenta tras el tiempo indicado por el proveedor. Revisa los contadores de mensajes unknown; no reenvíes una cola incierta a ciegas.

## Vincular pendientes del expediente v2.0

La vinculación es opcional y de solo lectura. Un operador debe verificar identidad y autoridad por un canal de confianza, obtener autorización para ese chat/expediente y registrar una referencia. El usuario debe haber iniciado el bot y obtenido su ID con /id. No existe un comando público que permita elegir arbitrariamente un expediente.

En un host con acceso local a ambas bases:

```bash
python3 skills/us-immigration-casework/scripts/telegram_bot.py link --db /private/bot/telegram.sqlite3 --chat-id CHAT_ID_VERIFIED --ledger /private/case/team/coordination.sqlite3 --case-id CASE_ID --actor ACTOR_ID --verification-ref AUTHORIZATION_REFERENCE
```

Usa un ID numérico real verificado en `--chat-id` y valores reales para los demás parámetros; el ejemplo es una plantilla, no un comando listo para ejecutar. En Docker necesitas montar deliberadamente la base del expediente en modo de solo lectura y usar su ruta dentro del contenedor; el compose de ejemplo no monta expedientes. /pendientes muestra solo ID/estado de tareas asignadas al actor o del propietario del expediente. No publica títulos sensibles, documentos, notas ni revisiones. Revocar al miembro bloquea las lecturas futuras. /borrar elimina el vínculo local.

## Preparar DS-260 y documentos

La guía privada está en [DS-260 y documentos](../../skills/us-immigration-casework/references/ds260-and-documents.md). Incluye hoja de trabajo y revisión por campos, exportación de borradores, plantillas Word con `{{KEY}}` y PDF AcroForm de texto. El DS-260 real se completa en CEAC; el solicitante revisa y firma. No hay compatibilidad automática con cualquier documento, escaneado, macro, firma, control PDF o formulario condicional.

Referencias: [Telegram Bot API](https://core.telegram.org/bots/api), [BotFather y funciones](https://core.telegram.org/bots/features), [Docker Compose y secretos](https://docs.docker.com/compose/how-tos/use-secrets/). Las pruebas del repositorio usan transporte simulado; no afirman que un bot real esté configurado o activo.
