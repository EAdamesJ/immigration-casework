# Ruta Consular en Cloudflare

Adaptador de webhook 2.1.1 para el bot de Telegram. Funciona en Workers con un Durable Object SQLite por conversación y alarmas persistentes para respuestas, recordatorios y limpieza. No necesita VPS, Docker, cron externo ni una computadora encendida. La disponibilidad depende de Cloudflare, Telegram, los límites de la cuenta y la operación del servicio; no hay garantía de entrega o disponibilidad absoluta.

## Funciones y límites

Conserva los 16 comandos del bot: tareas personales, zona IANA, consentimiento de avisos, hasta 20 recordatorios futuros dentro de 90 días, práctica guiada B1/B2 e inmigrante, orientación DS-260/documentos, privacidad y borrado. Hasta 50 tareas de 120 caracteres, 15 comandos/minuto por chat y bandeja acotada. Los controles de identificadores son parciales; usa siempre títulos genéricos.

Solo atiende chats privados con remitente coincidente. No descarga archivos, guarda respuestas de entrevista, utiliza IA generativa, calcula probabilidades ni presenta formularios. Los expedientes locales de la skill, el OCR, el rellenado documental y la vinculación profesional SQLite del bot Python permanecen fuera de este adaptador. No hay migración automática de datos del bot Python, ni seguimiento automático de USCIS o del boletín.

## Desplegar tu propio bot

Requisitos: cuenta Cloudflare con Workers/Durable Objects disponibles, Node.js 24 y un bot propio de Telegram. No necesitas crear otro bot si ya lo tienes. Este adaptador no requiere cambiar su token existente. No ejecutes long polling al mismo tiempo que un webhook.

```bash
cd integrations/telegram/cloudflare
npm ci
npm run types
npm run check
npm test
npm run build
npx wrangler login
```

Edita `name`, `BOT_OPERATOR_CONTACT` y `BOT_PRIVACY_URL` en [wrangler.jsonc](wrangler.jsonc) para tu operador, nombre de Worker y dirección pública reales. La URL de privacidad debe ser la de tu despliegue, terminada en `/privacidad`. El ejemplo pertenece al proyecto Ruta Consular; no uses su identidad como operador de tu propia instancia. La fecha de compatibilidad 2026-10-30 es la última soportada por el runtime local usado en esta entrega.

```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put WEBHOOK_SECRET
npm run deploy
```

Introduce el token existente en el primer diálogo. Para `WEBHOOK_SECRET`, genera un valor aleatorio independiente de 32 a 256 caracteres de letras, números, guion o guion bajo; por ejemplo con un gestor de contraseñas. Consérvalo en ese gestor para registrar el webhook. Las credenciales van a Cloudflare Secrets; nunca en Git, argumentos del shell, capturas, incidencias o mensajes del bot. La CLI puede crear primero un Worker vacío al configurar el primer secreto; el despliegue posterior instala el código.

La página `/privacidad` se sirve con el contacto configurado, sin publicar un correo personal por defecto. El contacto público de este proyecto es su canal de incidencias: solicita allí un canal privado sin publicar datos personales. El operador debe revisar que la política describa su uso real, sus proveedores y sus obligaciones; la plantilla no certifica cumplimiento legal.

Comprueba `/health`: debe devolver `ready: true`. Este estado comprueba la presencia y formato de la configuración, no la validez del token ni el éxito de una entrega.

```bash
python3 configure_webhook.py --worker-url https://TU-WORKER.TU-SUBDOMINIO.workers.dev
```

El asistente pide el token y el secreto sin eco, comprueba la identidad del bot, la salud del Worker y una petición sintética de grupo que no genera mensajes. Luego registra `/telegram/webhook` con `secret_token`, `allowed_updates: ["message"]`, `max_connections: 1` y **sin descartar actualizaciones pendientes**. La verificación posterior usa `getWebhookInfo`. El secreto se compara antes de leer/procesar el cuerpo. No hay endpoint administrativo público.

Si la red de tu terminal no permite verificar el Worker, comprueba `/health` de forma independiente en el navegador. Solo después puedes añadir `--health-verified` para registrar por la API oficial sin la comprobación HTTP local. La salida declara que omitió esa prueba; no equivale a verificar entrega. Comprueba `getWebhookInfo` y realiza la prueba real en Telegram. No cambies la identidad del cliente ni evadas un bloqueo del proveedor.

## Prueba de uso

Abre tu bot, pulsa Iniciar y envía `/start`, `/nuevo Revisar documento` y `/pendientes`. Configura `/zona America/Santo_Domingo`, `/avisos activar` y `/recordar` con una fecha futura y un desplazamiento correcto. La programación usa alarmas, sin exigir interacción posterior. Con dos cuentas sintéticas verifica que sus tareas permanezcan separadas. No uses expedientes reales para probar.

La suite incluye aislamiento en SQLite real de workerd, deduplicación concurrente, reinicio/evicción, límites, borrado, entregas inciertas, 429, bloqueo del bot, consentimiento y zonas con cambios de horario. Telegram está simulado en estas pruebas; no prueban recepción en tu teléfono. La publicación no afirma pruebas de carga masiva.

## Operación y recuperación

El webhook confirma recepción únicamente después de guardar el cambio y programar una alarma. Los identificadores técnicos de actualización evitan repetir cambios durante siete días. Cada mensaje de salida se marca antes de contactar a Telegram. Solo un 429 explícito permite reintento después de `retry_after`; una respuesta ambigua se marca `unknown`, sin reenvío automático. Una interrupción durante el envío se considera incierta después de dos minutos. Puede perderse un aviso: no uses el bot como único recordatorio de un plazo oficial.

Los avisos requieren activación expresa; desactivarlos cancela pendientes, aunque un envío iniciado puede terminar. Las tareas y preferencias caducan después de 90 días sin comandos. `/borrar confirmar` elimina datos activos; su confirmación puede retener temporalmente el chat ID. Los elementos inciertos caducan a los siete días. El borrado no elimina historial de Telegram ni garantiza eliminación inmediata de copias del proveedor. No se registra texto de mensajes, tokens o documentos en logs de aplicación; las trazas e invocation logs están desactivados. Los errores de almacenamiento producen un evento genérico.

Comprueba errores y consumo en Cloudflare. No se cambia el plan ni se autoriza una compra: el uso está sujeto a las cuotas y condiciones de la cuenta existente. Un plan gratuito tiene límites; en cuentas de pago pueden existir cargos por consumo. No se promete capacidad ilimitada o coste cero.

Para actualizar: instala con `npm ci`, genera tipos, ejecuta las comprobaciones y despliega con `npm run deploy` (conserva variables). Guarda las credenciales en el gestor del operador. Para volver al bot Python, detén primero esta integración, elimina el webhook explícitamente mediante Telegram y solo después inicia long polling; no descartes pendientes por defecto. No borres la migración `v1` ni renombres la clase `ConsularChat` de un despliegue existente sin un plan de migración.

Referencias oficiales: [Workers](https://developers.cloudflare.com/workers/), [Durable Objects SQLite](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/), [Alarmas](https://developers.cloudflare.com/durable-objects/api/alarms/), [Tarifas y límites](https://developers.cloudflare.com/durable-objects/platform/pricing/), [Telegram setWebhook](https://core.telegram.org/bots/api#setwebhook).
