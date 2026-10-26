# Integración del dashboard con Apps Script

## Flujo implementado

1. Flask conserva la protección CSRF, las reglas de aprobación/rechazo y la transición de `PENDIENTE` a `APROBADO` o `DESCARTADO`.
2. Python escribe el estado en Google Sheets por `CÓDIGO` único. Si la escritura da timeout, vuelve a leer la fila por código antes de decidir si puede continuar.
3. Solo después de confirmar el estado, el backend envía `codigo` y `accion` a `doPost(e)`. Apps Script vuelve a leer la pestaña y el estado guardado; no confía en un estado enviado por el navegador.
4. Un `ScriptLock` compartido con `alCambiarEstado(e)` serializa la generación del correo/PDF. `NOTIFICADO` evita el reenvío. Un estado `ERROR` o una marca `ENVIANDO...` huérfana puede reintentarse cuando ya no existe una ejecución con el bloqueo.
5. Si el POST expira, Python consulta primero el estado persistido con la acción `consultar`; nunca repite automáticamente un envío de resultado incierto.
6. El endpoint separado de reintento solo acepta registros con estado final y notificación pendiente; no vuelve a escribir el estado.

## Configuración servidor-servidor

La llamada del cliente exige una URL y un secreto. La causa del aviso original era que `.env` no se cargaba en el arranque `python app.py`. Ahora la aplicación carga el archivo explícitamente con `load_dotenv` y el cliente usa exclusivamente `APPS_SCRIPT_SHARED_SECRET` para el valor local.

- `APPS_SCRIPT_WEB_APP_URL`: URL HTTPS exacta existente, formato `https://script.google.com/macros/s/DEPLOYMENT_ID/exec`.
- `APPS_SCRIPT_SHARED_SECRET`: mismo valor que la propiedad Apps Script `PYTHON_WEBHOOK_TOKEN`. No lo guardes en HTML, navegador ni historial de Git.

La URL y el secreto del backend se leen del archivo local `.env`, excluido de Git. `python app.py` carga el archivo mediante `load_dotenv(Path(__file__).resolve().parent / '.env', override=False)` antes de inicializar Flask o importar el cliente de Apps Script. La credencial Python usa exclusivamente `APPS_SCRIPT_SHARED_SECRET`; debe coincidir con la propiedad remota `PYTHON_WEBHOOK_TOKEN`.

`SPREADSHEET_ID` es opcional en Apps Script: si no se define como propiedad, usa el ID del spreadsheet del proyecto. `SHEET_NAME` es opcional; sin ella se usa la primera pestaña. Define `SHEET_NAME` solo si la hoja operativa no es la primera.

No uses `credenciales.json` como secreto de este webhook ni expongas el token como variable JavaScript. En el arranque Python registra categorías de configuración sin valores; las solicitudes registran host/categoría/estado HTTP sin token ni URL de deployment completa. El cliente distingue configuración ausente/inválida, rechazo de autenticación, timeout, errores HTTP y respuesta/contrato inválido (incluida página HTML de `doGet` en lugar de JSON de `doPost`).

## Actualizar la implementación existente

1. Abre el proyecto Apps Script ligado al spreadsheet usado por el dashboard y conserva los archivos HTML, plantillas, firmas y activadores existentes.
2. Sustituye/actualiza únicamente el código de `Code.gs` con `apps_script/Code.gs` de este proyecto. No borres el HTML del formulario ni reinstales los activadores.
3. En **Configuración del proyecto → Propiedades de la secuencia de comandos**, verifica `PYTHON_WEBHOOK_TOKEN`; agrega `SHEET_NAME` solo si la pestaña operativa no es la primera. Confirma que `SPREADSHEET_ID`, si está definido, apunta al mismo spreadsheet que utiliza Python.
4. En **Implementar → Gestionar implementaciones**, edita la implementación web existente, selecciona una nueva versión y actualízala. Mantén la URL de `/exec` existente y la identidad que ejecuta la aplicación con permisos para Spreadsheet, Drive, Docs y envío de correo.
5. La implementación web debe aceptar el POST del servidor. Si se publica con acceso externo, el secreto obligatorio de `doPost` autentica las llamadas; no se envía al navegador. Aplica además las políticas de acceso de la organización.
6. Verifica que `.env` local tenga `APPS_SCRIPT_WEB_APP_URL` y `APPS_SCRIPT_SHARED_SECRET`; reinicia Flask con `python app.py`. Ningún valor secreto debe aparecer en logs.
7. Verifica en Apps Script que sigue instalado el activador de edición `alCambiarEstado(e)` y que se ejecuta con la cuenta propietaria del flujo.

## Verificación funcional en un entorno controlado

Usa códigos de prueba y una bandeja de correo controlada; el flujo de aprobación genera un PDF real en Drive y envía correo real.

- **Aprobación:** confirma una solicitud válida; verifica `APROBADO`, un correo con el PDF adjunto, y `NOTIFICADO = SÍ`.
- **Rechazo:** confirma el rechazo; verifica `DESCARTADO`, el correo de rechazo sin PDF y `NOTIFICADO = SÍ`.
- **Cancelación:** cancela el cuadro SweetAlert2; no debe salir solicitud al backend ni cambiar la fila.
- **Repetición:** haz doble clic o repite la llamada; debe conservarse un único estado y no reenviar si `NOTIFICADO` ya está registrado.
- **Fallo de correo/configuración:** el estado final debe conservarse, la interfaz debe indicar “El registro fue actualizado, pero no se pudo enviar la notificación” y mostrar la opción de reintento.
- **Reintento:** corrige el fallo, elige “Reintentar notificación”; debe procesar solo el correo/PDF pendiente y no volver a escribir el estado.
- **Timeout:** confirma que el backend consulta `NOTIFICADO` antes de permitir un reintento. Si la consulta indica `ENVIANDO...`, espera y vuelve a comprobar; no dispares envíos en paralelo.
- **Concurrencia:** inicia una edición manual y una solicitud del dashboard para el mismo registro; el bloqueo compartido debe permitir un solo procesamiento.

Las pruebas automatizadas cubren la carga de `.env`, el flujo Flask→escritura→solicitud HTTPS `/exec`, autorización, respuestas HTML/contrato viejo, errores, reintento y consulta posterior a timeout. Son pruebas controladas con HTTP simulado: no generan correo ni PDF real.

## Estado de verificación real

El arranque con `.venv` carga `.env` y la validación local confirma ambas variables sin imprimir el secreto. La prueba HTTP de solo lectura anterior alinea con que el deployment todavía respondió 401/login; no se ha confirmado acceso autenticado ni la ejecución remota de `doPost(e)`. Verifica la propiedad de Apps Script **`PYTHON_WEBHOOK_TOKEN`** contra el valor local de `APPS_SCRIPT_SHARED_SECRET` y el acceso del deployment. Luego reinicia Flask y realiza una consulta `consultar` autenticada antes de probar correo/PDF. La carga local correcta no prueba por sí sola que se envió una notificación.
