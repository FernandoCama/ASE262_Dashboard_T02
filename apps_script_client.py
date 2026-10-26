"""Backend client for the Apps Script notification/PDF workflow."""

import logging
import os
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


URL_VARIABLES = (
    'APPS_SCRIPT_WEB_APP_URL',
    'APPS_SCRIPT_URL',
    'GOOGLE_APPS_SCRIPT_URL',
    'APPS_SCRIPT_EXEC_URL',
)
TOKEN_VARIABLE = 'APPS_SCRIPT_SHARED_SECRET'


# Excepción de integración que clasifica errores sin exponer los secretos configurados.
class ErrorAppsScript(RuntimeError):
    """Apps Script configuration or invocation error with a safe category."""

    def __init__(self, mensaje, categoria):
        super().__init__(mensaje)
        self.categoria = categoria


    # Selecciona la primera variable configurada de una lista de nombres compatibles.
def _primera_variable(nombres):
    for nombre in nombres:
        valor = os.environ.get(nombre, '').strip()
        if valor:
            return valor, nombre
    return '', nombres[0]


# Valida la URL HTTPS y el secreto compartido requeridos para la integración.
def _configuracion():
    url, _ = _primera_variable(URL_VARIABLES)
    token = os.environ.get(TOKEN_VARIABLE, '').strip()
    if not url:
        raise ErrorAppsScript(
            'Falta la URL de implementación de Apps Script (variable APPS_SCRIPT_WEB_APP_URL).',
            'configuracion_url_ausente',
        )
    if not token:
        raise ErrorAppsScript(
            f'Falta el secreto compartido del servidor (variable {TOKEN_VARIABLE}).',
            'configuracion_secreto_ausente',
        )
    parsed = urlparse(url)
    if (
        parsed.scheme != 'https'
        or parsed.hostname != 'script.google.com'
        or not parsed.path.startswith('/macros/s/')
        or not parsed.path.endswith('/exec')
    ):
        raise ErrorAppsScript(
            'La URL debe ser la URL HTTPS de implementación de Apps Script terminada en /macros/s/.../exec.',
            'configuracion_url_invalida',
        )
    return url, token


# Envía la acción a Apps Script y valida estado HTTP, JSON y campos de respuesta.
def _solicitar(codigo, accion):
    url, token = _configuracion()
    try:
        respuesta = requests.post(
            url,
            json={'codigo': str(codigo).strip(), 'accion': accion, 'token': token},
            timeout=(5, 90),
        )
    except requests.Timeout:
        logger.warning('Apps Script agotó el tiempo de conexión/lectura; acción=%s.', accion)
        raise
    except requests.ConnectionError as error:
        logger.warning('No se pudo conectar con Apps Script; acción=%s.', accion)
        raise ErrorAppsScript(
            'No se pudo conectar con la implementación de Apps Script.',
            'conexion_fallida',
        ) from error
    except requests.RequestException as error:
        logger.warning('Falló la solicitud HTTP a Apps Script; acción=%s.', accion)
        raise ErrorAppsScript(
            'Falló la solicitud HTTP a Apps Script.', 'error_http'
        ) from error

    url_respuesta = getattr(respuesta, 'url', '')
    url_final = urlparse(url_respuesta) if isinstance(url_respuesta, str) else None
    if url_final and url_final.hostname in {'accounts.google.com', 'myaccount.google.com'}:
        logger.error('Apps Script redirigió a autenticación de Google; acción=%s.', accion)
        raise ErrorAppsScript(
            'La implementación exige una sesión Google en lugar de aceptar la llamada del servidor. Revisa quién puede acceder y la cuenta de ejecución del deployment.',
            'autenticacion_rechazada',
        )
    if respuesta.status_code in (401, 403):
        logger.error('Apps Script rechazó la autenticación; acción=%s, HTTP=%s.', accion, respuesta.status_code)
        raise ErrorAppsScript(
            'Apps Script rechazó la autenticación. Verifica que PYTHON_WEBHOOK_TOKEN coincida con el secreto del backend.',
            'autenticacion_rechazada',
        )
    if respuesta.status_code == 404:
        logger.error('La URL configurada no corresponde a una implementación web vigente; acción=%s.', accion)
        raise ErrorAppsScript(
            'Apps Script respondió 404. Verifica la URL /exec y vuelve a publicar la implementación.',
            'implementacion_no_encontrada',
        )
    if not respuesta.ok:
        logger.error('Apps Script respondió con HTTP %s; acción=%s.', respuesta.status_code, accion)
        raise ErrorAppsScript(
            f'Apps Script respondió con HTTP {respuesta.status_code}.', 'error_http'
        )

    try:
        resultado = respuesta.json()
    except ValueError as error:
        logger.error(
            'Respuesta no JSON desde Apps Script (posible doPost ausente o deployment antiguo); acción=%s, HTTP=%s.',
            accion,
            respuesta.status_code,
        )
        raise ErrorAppsScript(
            'La respuesta de Apps Script no es JSON. La URL podría servir doGet o una versión antigua sin doPost; actualiza la implementación /exec.',
            'respuesta_invalida_sin_dopost',
        ) from error
    if not isinstance(resultado, dict):
        raise ErrorAppsScript(
            'Apps Script devolvió una respuesta JSON con formato no válido.',
            'respuesta_json_invalida',
        )
    if resultado.get('ok') is False:
        error_remoto = str(resultado.get('error') or '')
        if 'autorizado' in error_remoto.lower() or 'token' in error_remoto.lower():
            logger.error('Apps Script rechazó el token; acción=%s.', accion)
            raise ErrorAppsScript(
                'Apps Script rechazó la autenticación. Verifica que PYTHON_WEBHOOK_TOKEN coincida con el secreto del backend.',
                'autenticacion_rechazada',
            )
        if resultado.get('procesando') is True:
            logger.info('Apps Script ya procesa una notificación para la solicitud actual.')
            return resultado
        # Un fallo de correo incluye el estado ya guardado y el estado ERROR.
        if resultado.get('estado_guardado') is True and 'notificacion_enviada' in resultado:
            logger.warning('Apps Script confirmó estado guardado, pero falló el envío; acción=%s.', accion)
            return resultado
        logger.error('Apps Script devolvió error de aplicación; acción=%s.', accion)
        raise ErrorAppsScript(
            'Apps Script recibió la solicitud, pero devolvió un error de aplicación.',
            'error_apps_script',
        )

    campos_requeridos = {'estado_guardado', 'notificado', 'notificacion_enviada'}
    if not campos_requeridos.issubset(resultado):
        logger.error('Respuesta de Apps Script sin campos requeridos; posible deployment antiguo.')
        raise ErrorAppsScript(
            'La respuesta de Apps Script no contiene el contrato esperado. Actualiza la implementación para incluir doPost.',
            'contrato_invalido_o_dopost_antiguo',
        )
    if accion == 'consultar' and 'procesando' not in resultado:
        raise ErrorAppsScript(
            'La respuesta de consulta de Apps Script está incompleta.',
            'contrato_invalido_o_dopost_antiguo',
        )
    return resultado


# Traduce la respuesta de Apps Script al formato de notificación utilizado por Flask.
def _a_notificacion(resultado):
    notificado = resultado.get('notificado') is True
    enviado = resultado.get('notificacion_enviada') is True
    ya_estaba = resultado.get('ya_estaba_notificado') is True or (
        notificado and not enviado
    )
    pendiente = resultado.get('estado_final') is True and not notificado
    return {
        'estado_guardado': resultado.get('estado_guardado'),
        'enviado': enviado,
        'registrado': notificado,
        'ya_estaba': ya_estaba,
        'pendiente': pendiente,
        'procesando': resultado.get('procesando') is True,
        'estado': resultado.get('estado_notificado', ''),
        'mensaje': resultado.get('mensaje', ''),
        'error': resultado.get('error', ''),
        'error_categoria': 'envio_fallido' if resultado.get('error') else '',
    }


# Consulta el resultado guardado tras un timeout, sin volver a enviar el correo automáticamente.
def _consultar_tras_timeout(codigo):
    try:
        resultado = _solicitar(codigo, 'consultar')
    except (requests.RequestException, ErrorAppsScript) as error:
        categoria = error.categoria if isinstance(error, ErrorAppsScript) else 'timeout_consulta_fallida'
        logger.error('No se pudo consultar estado persistido tras timeout; categoría=%s.', categoria)
        return {
            'enviado': False,
            'registrado': False,
            'ya_estaba': False,
            'pendiente': True,
            'procesando': False,
            'estado': '',
            'mensaje': (
                'La solicitud agotó el tiempo y no se pudo consultar su resultado. '
                'No se repetirá el envío automáticamente.'
            ),
            'error': 'timeout_sin_confirmacion',
            'error_categoria': categoria,
        }

    notificacion = _a_notificacion(resultado)
    if notificacion['registrado']:
        notificacion.update(
            enviado=False,
            ya_estaba=True,
            pendiente=False,
            mensaje='Apps Script confirmó que la notificación quedó registrada.',
        )
    elif notificacion['procesando']:
        notificacion.update(
            pendiente=True,
            mensaje=(
                'La notificación continúa en procesamiento. '
                'Consulta nuevamente antes de solicitar otro envío.'
            ),
            error_categoria='timeout_resultado_persistido',
        )
    else:
        notificacion.update(
            pendiente=True,
            mensaje=(
                'Apps Script no confirmó la notificación tras el tiempo de espera. '
                'Se requiere una consulta o reintento explícito.'
            ),
        )
    return notificacion


# Solicita procesar un aviso; ante timeout consulta primero el estado para prevenir duplicados.
def procesar_notificacion(codigo):
    """Pide a Apps Script procesar el estado ya guardado para un código.

    Si la petición expira, primero consulta el estado persistido y nunca repite
    automáticamente el envío, evitando duplicados por una respuesta perdida.
    """
    try:
        resultado = _solicitar(codigo, 'procesar')
    except requests.Timeout:
        return _consultar_tras_timeout(codigo)
    except ErrorAppsScript as error:
        return {
            'enviado': False,
            'registrado': False,
            'ya_estaba': False,
            'pendiente': True,
            'procesando': False,
            'estado': '',
            'mensaje': str(error),
            'error': str(error),
            'error_categoria': error.categoria,
        }
    notificacion = _a_notificacion(resultado)
    if notificacion['error']:
        notificacion['mensaje'] = (
            'El estado quedó guardado, pero Apps Script no pudo confirmar el envío. '
            'Revisa el error de Apps Script y vuelve a intentar solo la notificación.'
        )
        notificacion['error_categoria'] = 'envio_fallido'
    return notificacion


# Diagnostica si la integración está configurada sin registrar ni devolver el secreto.
def diagnosticar_configuracion():
    """Validate effective config without returning or logging secret values."""
    try:
        url, _ = _configuracion()
    except ErrorAppsScript as error:
        logger.warning('Configuración Apps Script no lista; categoría=%s.', error.categoria)
        return False, error.categoria
    logger.info('Configuración Apps Script lista; host=%s, ruta /exec presente.', urlparse(url).hostname)
    return True, ''