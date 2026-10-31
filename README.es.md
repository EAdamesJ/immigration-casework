# Immigration Casework

**Una skill para convertir avisos y documentos dispersos en un expediente verificable y un próximo paso concreto.**

[English](README.md) · [Compatibilidad](docs/compatibility.md) · [Ejemplos en español](examples/prompts.es.md)

Funciona como un método de investigación y preparación para agentes compatibles con Agent Skills. Se centra en peticiones familiares y procesos consulares de Estados Unidos. No es un bufete, no se atribuye licencia profesional y no garantiza resultados ni presenta trámites por sí sola.

## v2.0 Conectores calendario avisos y colaboración

La versión añade calendario ICS privado, coordinación local y adaptadores opcionales para herramientas disponibles en el agente. La instalación no conecta cuentas, comparte expedientes ni activa avisos.

| Módulo | Resultado |
| --- | --- |
| [Conectores](skills/us-immigration-casework/references/connectors-and-hosts.md) | Preparación de acciones para Google/Outlook Calendar, Gmail/Outlook y recordatorios personales; el agente usa la herramienta autenticada disponible |
| [Calendario y avisos](skills/us-immigration-casework/references/calendar-and-notifications.md) | Fechas documentadas, zonas horarias, exportación ICS y cola con autorizaciones, comprobación previa y resultados registrados |
| [Colaboración](skills/us-immigration-casework/references/professional-collaboration.md) | Responsables por expediente, tareas, revisión independiente, versiones y detección de conflictos |
| [Comandos](skills/us-immigration-casework/references/coordination-tools.md) | Base SQLite privada, registro de cambios y protocolo de envío que detiene resultados inciertos |

El calendario no calcula plazos legales ni instala un programador. Una exportación no activa notificaciones. La revisión se vincula al hash de una versión concreta; editarla crea un borrador nuevo. Los roles locales no autentican personas ni sustituyen los permisos del servicio compartido. La base no está cifrada y el registro no es inmutable. Los conectores generan solicitudes para el agente; no incluyen OAuth, credenciales, servidor, sincronización bidireccional o envío autónomo. Outlook admite citas con hora y un aviso en este adaptador; las funciones no disponibles se mantienen bloqueadas o usan el archivo ICS.

Puede hacer falta instalar `tzdata` para zonas horarias, especialmente en Windows. Para actualizar una copia local, revisar los cambios y ejecutar `python3 scripts/install.py --target all --replace`; se conserva una copia anterior. Los expedientes v1.x no necesitan migración automática. Las pruebas usan datos sintéticos y capacidades simuladas; no envían correos ni crean citas reales.

Ejemplo: “Usa us-immigration-casework para organizar las tareas de este expediente, preparar un calendario con las fechas verificadas y dejar un paquete para revisión independiente. Usa conectores solo para las acciones y destinos que autorice.”

## v1.2 DS-160 OCR negativas y exportaciones

La nueva versión añade un borrador estructurado del DS-160, revisión de fechas y confirmaciones del solicitante, OCR local de documentos, análisis de negativas y paquetes para revisión profesional. La plantilla cubre campos seleccionados y debe contrastarse con cada pregunta del CEAC vigente. No firma ni presenta solicitudes.

| Módulo | Resultado |
| --- | --- |
| [DS-160](skills/us-immigration-casework/references/ds160-preparation.md) | Información pendiente, referencias documentales, coherencia y confirmación del solicitante |
| [OCR](skills/us-immigration-casework/references/document-ocr.md) | Texto por página, coordenadas, confianza y huella del original; todo comienza sin verificar |
| [Negativas](skills/us-immigration-casework/references/refusal-analysis.md) | Rutas separadas para 214(b), 221(g), otros fundamentos y varios simultáneos |
| [Exportaciones](skills/us-immigration-casework/references/export-packages.md) | Markdown, HTML, JSON y ZIP; PDF y DOCX con dependencias opcionales |

Consulta el [contrato de comandos](skills/us-immigration-casework/references/preparation-tools.md) y copia las plantillas JSON a una carpeta privada. El OCR requiere Tesseract y Poppler para PDF; los datos de idioma se instalan aparte. PDF usa ReportLab y DOCX usa python-docx. La instalación de la skill no instala esas dependencias. El ZIP no está cifrado ni anonimizado y no se comparte automáticamente. Las pruebas básicas no requieren dependencias opcionales. Un trabajo separado de Ubuntu instala los motores y ejecuta tres pruebas sintéticas de OCR y exportación PDF/DOCX.

Ejemplo: “Usa us-immigration-casework para preparar mi DS-160, revisar la negativa adjunta y exportar un borrador para mi abogado. Conserva las dudas del OCR y marca los datos faltantes.”

## Qué incluye

- Reconstrucción del expediente y cronología con estados de verificación.
- Separación de USCIS, NVC, consulado, visa y admisión.
- Revisión de formularios, requerimientos, contradicciones y plazos documentados.
- Preparación de solicitudes humanitarias, cartas para pedir respaldo médico y consultas congresionales.
- Plantillas de informes, matrices de evidencias, fuentes, acciones y respuestas.
- Herramientas locales para calcular esperas, revisar estructura y coherencia, clasificar dominios y ocultar ciertos identificadores en texto.
- Instrucciones para investigar fuentes actuales y señalar cuándo se necesita revisión profesional.

## Instalación

Revisa los archivos antes de instalar:

```bash
git clone https://github.com/EAdamesJ/immigration-casework.git
cd immigration-casework
python3 scripts/install.py --target all --dry-run
python3 scripts/install.py --target all
```

Puedes sustituir `all` por `codex`, `claude` o `deepseek`. En Windows, usa `py -3` si ese es tu lanzador de Python. Las herramientas requieren Python 3.10+; las instrucciones Markdown pueden utilizarse sin Python.

| Entorno | Instalación personal |
| --- | --- |
| Codex | `~/.agents/skills/us-immigration-casework/` |
| Claude Code | `~/.claude/skills/us-immigration-casework/` |
| DeepSeek Harness | `${DSH_HOME:-~/.dsh}/skills/us-immigration-casework/` |

Para instalar en un proyecto, añade `--scope project --project-root /ruta/absoluta`. El instalador copia archivos locales; no instala aplicaciones, modifica configuraciones ni inicia sesiones. Si hay una versión distinta, se detiene. Usa `--replace` para conservarla como respaldo y actualizar. Los respaldos quedan fuera del directorio que descubre skills.

La compatibilidad del formato y las rutas se investigó en fuentes oficiales. Las pruebas automáticas verifican las herramientas y copias locales; no equivalen a ejecutar los tres agentes con sus modelos. Claude chat/Cowork y entornos gestionados en la nube usan mecanismos propios de instalación. Consulta los [límites concretos](docs/compatibility.md).

## Cómo usarla

En Codex escribe `$us-immigration-casework`; en Claude Code, `/us-immigration-casework`. En DeepSeek Harness selecciónala desde su interfaz de skills o pide usarla por su nombre.

```text
Usa us-immigration-casework para revisar los avisos que adjunto.
Reconstruye la cronología, identifica plazos y contradicciones,
consulta las fuentes oficiales necesarias y prepara un informe
con evidencias faltantes y el siguiente paso concreto.
```

Las instrucciones internas están principalmente en inglés para facilitar portabilidad; el agente debe responder en tu idioma. Las plantillas incluyen informes bilingües, cartas dirigidas a autoridades en inglés y un resumen profesional en español.

## Privacidad y límites

Guarda los expedientes reales fuera del repositorio público y de la skill. Los scripts incluidos no usan la red; el servicio de IA y las herramientas del agente tienen sus propias condiciones de tratamiento de datos. No confundas ese comportamiento con una garantía de que toda la conversación permanece en tu dispositivo.

La ocultación de identificadores es parcial: no elimina por sí sola nombres, domicilios, diagnósticos, imágenes o metadatos. Revisa manualmente antes de compartir. El cálculo de espera no determina plazos legales ni predice decisiones. La revisión estructural no certifica elegibilidad ni autenticidad.

La skill prepara resultados para revisar. Las firmas, certificaciones, autorizaciones y decisiones profesionales corresponden a sus responsables reales. Nunca adjuntes documentos personales a incidencias o solicitudes de cambio.

## Verificación y participación

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
```

Se aceptan mejoras con casos inventados, plantillas, traducciones y reportes de compatibilidad reproducibles. Consulta [cómo contribuir](CONTRIBUTING.md) y la [guía de evaluación](evals/README.md).

Creado por [JeyTid](https://github.com/EAdamesJ). Licencia [MIT](LICENSE). Proyecto independiente, sin respaldo implícito de USCIS, otras autoridades o proveedores de IA.

## v1.1 — Visitor preparation / Preparación B1/B2

B1/B2 intake, qualitative preparation coverage, adaptive interview practice in English/Spanish, and personalized Visa Bulletin comparisons are included. Read the [visitor workflow](skills/us-immigration-casework/references/visitor-preparation.md), [interview guide](skills/us-immigration-casework/references/interview-simulator.md), [bulletin guide](skills/us-immigration-casework/references/visa-bulletin.md) and [local command contract](skills/us-immigration-casework/references/visitor-tools.md). Preparation is not approval probability; bulletin snapshots require current official-source verification.
