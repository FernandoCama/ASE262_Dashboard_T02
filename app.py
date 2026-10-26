from datetime import datetime
import json
import os
import secrets
import threading
from pathlib import Path

from dotenv import load_dotenv

# Carga primero las variables locales para que los servicios importados las encuentren.
# Cargar la configuración del proyecto antes de inicializar Flask o importar
# cualquier servicio que lea variables de entorno.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env', override=False)

from flask import Flask, jsonify, render_template, request, session

from apps_script_client import diagnosticar_configuracion, procesar_notificacion
from conexion_sheets import (
    ErrorRegistro,
    actualizar_estado_registro,
    obtener_registro_por_codigo,
    obtener_datos,
)
from analisis import LIMITE_GASTO, calcular_kpis
from graficos import colores_para_estados, generar_graficos, grafico_estados_interactivo

# Inicialización de Flask, seguridad de sesión y bloqueo de acciones simultáneas.
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)
_approval_workflow_lock = threading.Lock()

diagnosticar_configuracion()


# Genera un token de sesión para proteger las peticiones que modifican registros.
def _csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


# Convierte el DataFrame a listas JSON para que la plantilla pueda usarlo en JavaScript.
def _serializar_registros(df):
    if df is None or df.empty:
        return [], []
    datos = json.loads(
        df.to_json(
            orient='split',
            date_format='iso',
            date_unit='s',
            force_ascii=False,
            double_precision=15,
        )
    )
    return datos['columns'], datos['data']


# Ruta principal: carga la hoja, calcula indicadores y prepara los gráficos del panel.
@app.route('/')
def inicio():
    """Carga los datos, calcula los indicadores y muestra el dashboard."""
    error_carga = None
    df = None
    grafico_html = "" # Contenido HTML del gráfico interactivo; queda vacío si no se genera.

    try:
        df = obtener_datos()
    except Exception:
        app.logger.exception('No se pudieron obtener los datos de Google Sheets.')
        error_carga = (
            'No se pudieron cargar los datos de Google Sheets. '
            'Revisa la conexión y vuelve a intentarlo.'
        )

    kpis = calcular_kpis(df)
    estados_conocidos = list(kpis['conteo_estados'].keys()) + [
        'APROBADO', 'PENDIENTE', 'DESCARTADO'
    ]
    colores_estados = colores_para_estados(estados_conocidos)

    try:
        # Conserva una imagen PNG como alternativa si el gráfico interactivo no está disponible.
        generar_graficos(df)
        
        # Solo genera Plotly cuando la hoja contiene registros.
        if df is not None and not df.empty:
            figura_plotly = grafico_estados_interactivo(df)
            grafico_html = figura_plotly.to_html(
                full_html=False,
                include_plotlyjs=False,
                config={'displayModeBar': False, 'responsive': True},
                post_script="""
                    (() => {
                        const plot = document.getElementById('{plot_id}');
                        if (!plot) return;

                        const tooltip = document.createElement('div');
                        tooltip.className = 'chart-hover-card';
                        tooltip.setAttribute('role', 'status');
                        tooltip.setAttribute('aria-live', 'polite');
                        document.body.appendChild(tooltip);

                        let pointerX = 0;
                        let pointerY = 0;
                        plot.addEventListener('pointermove', event => {
                            pointerX = event.clientX;
                            pointerY = event.clientY;
                        });

                        plot.on('plotly_hover', eventData => {
                            const point = eventData.points && eventData.points[0];
                            if (!point) return;

                            const [percentValue, barColor] = point.customdata;
                            const percent = Number(percentValue);
                            const colorHex = String(barColor || '#101a31');
                            const rgb = colorHex.match(/[\\da-f]{2}/gi)?.map(value => parseInt(value, 16)) || [16, 26, 49];
                            const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
                            tooltip.style.backgroundColor = colorHex;
                            tooltip.style.borderColor = colorHex;
                            tooltip.style.color = luminance > 0.62 ? '#17233c' : '#ffffff';
                            tooltip.textContent = `${point.y}\\nCantidad: ${point.x}\\nPorcentaje: ${percent.toFixed(1)}%`;
                            tooltip.classList.add('is-visible');

                            const padding = 12;
                            const left = Math.min(pointerX + 16, window.innerWidth - tooltip.offsetWidth - padding);
                            const top = Math.min(pointerY + 16, window.innerHeight - tooltip.offsetHeight - padding);
                            tooltip.style.left = `${Math.max(padding, left)}px`;
                            tooltip.style.top = `${Math.max(padding, top)}px`;
                        });

                        // plotly_unhover se dispara al cruzar espacios entre barras;
                        // mantener la tarjeta hasta salir del gráfico evita parpadeos.
                        plot.addEventListener('pointerleave', () => {
                            tooltip.classList.remove('is-visible');
                        });
                    })();
                """,
            )
            
    except Exception:
        app.logger.exception('No se pudo generar el gráfico de estados.')

    # Mantiene todas las columnas para construir la tabla resumida y el detalle del modal.
    columnas, registros = _serializar_registros(df)

    return render_template(
        'dashboard.html',
        kpis=kpis,
        columnas=columnas,
        registros=registros,
        limite_gasto=LIMITE_GASTO,
        error_carga=error_carga,
        actualizado=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        version_grafico=int(datetime.now().timestamp()),
        grafico_interactivo=grafico_html,  # Entrega a la plantilla el gráfico ya renderizado.
        colores_estados=colores_estados,
        csrf_token=_csrf_token(),
    )


# Endpoints de aprobación y rechazo: valida la sesión, guarda el estado y solicita el aviso.
@app.post('/api/registros/aprobar')
@app.post('/api/registros/rechazar')
def cambiar_estado_registro_route():
    """Cambia por código único un registro pendiente y notifica el resultado."""
    token_sesion = session.get('csrf_token')
    token_solicitud = request.headers.get('X-CSRF-Token', '')
    if not token_sesion or not secrets.compare_digest(token_sesion, token_solicitud):
        return jsonify(ok=False, error='La sesión expiró. Actualiza el panel e inténtalo nuevamente.'), 403
    if not request.is_json:
        return jsonify(ok=False, error='La solicitud debe enviarse como JSON.'), 415

    datos = request.get_json(silent=True) or {}
    codigo = str(datos.get('codigo', '')).strip()
    if not codigo:
        return jsonify(ok=False, error='El código del registro es obligatorio.'), 400
    nuevo_estado = 'APROBADO' if request.path.endswith('/aprobar') else 'DESCARTADO'

    with _approval_workflow_lock:
        try:
            registro = actualizar_estado_registro(codigo, nuevo_estado, LIMITE_GASTO)
        except ErrorRegistro as error:
            return jsonify(ok=False, error=str(error)), error.status_code
        except Exception:
            app.logger.exception('No se pudo actualizar el registro en Google Sheets.')
            try:
                registro = obtener_registro_por_codigo(codigo)
            except Exception:
                registro = None
            if not registro or registro['estado'] != nuevo_estado:
                return jsonify(
                    ok=False,
                    error='No se pudo confirmar el cambio en Google Sheets. Verifica el registro antes de reintentar.',
                ), 502

        if not registro['tiene_columna_notificado']:
            notificacion = {
                'enviado': False,
                'registrado': False,
                'ya_estaba': False,
                'pendiente': True,
                'procesando': False,
                'mensaje': 'La hoja no tiene la columna NOTIFICADO.',
            }
        elif _valor_notificado(registro['notificado']):
            notificacion = {
                'enviado': False,
                'registrado': True,
                'ya_estaba': True,
                'pendiente': False,
                'procesando': False,
                'mensaje': 'La hoja ya indica que este registro fue notificado; no se envió otro correo.',
            }
        else:
            notificacion = procesar_notificacion(codigo)
            if notificacion.get('error'):
                app.logger.warning(
                    'El estado %s se guardó; Apps Script no confirmó la notificación para %s: %s',
                    nuevo_estado,
                    codigo,
                    notificacion['error'],
                )

    return jsonify(
        ok=True,
        guardado=True,
        aprobado=nuevo_estado == 'APROBADO',
        rechazado=nuevo_estado == 'DESCARTADO',
        codigo=codigo,
        estado=nuevo_estado,
        notificacion=notificacion,
    )


# Endpoint independiente para reintentar un aviso sin volver a modificar el estado guardado.
@app.post('/api/registros/notificacion/reintentar')
def reintentar_notificacion_route():
    """Reintenta solo la notificación pendiente de un registro ya finalizado."""
    token_sesion = session.get('csrf_token')
    token_solicitud = request.headers.get('X-CSRF-Token', '')
    if not token_sesion or not secrets.compare_digest(token_sesion, token_solicitud):
        return jsonify(ok=False, error='La sesión expiró. Actualiza el panel e inténtalo nuevamente.'), 403
    if not request.is_json:
        return jsonify(ok=False, error='La solicitud debe enviarse como JSON.'), 415

    datos = request.get_json(silent=True) or {}
    codigo = str(datos.get('codigo', '')).strip()
    if not codigo:
        return jsonify(ok=False, error='El código del registro es obligatorio.'), 400

    with _approval_workflow_lock:
        try:
            registro = obtener_registro_por_codigo(codigo)
        except ErrorRegistro as error:
            return jsonify(ok=False, error=str(error)), error.status_code
        except Exception:
            app.logger.exception('No se pudo verificar el estado antes de reintentar la notificación.')
            return jsonify(ok=False, error='No se pudo verificar el estado guardado en Google Sheets.'), 502

        if registro['estado'] not in {'APROBADO', 'DESCARTADO'}:
            return jsonify(ok=False, error='Solo se puede notificar un registro con estado final.'), 409
        if not registro['tiene_columna_notificado']:
            return jsonify(ok=False, error='La hoja no tiene la columna NOTIFICADO.'), 409
        if _valor_notificado(registro['notificado']):
            notificacion = {
                'enviado': False,
                'registrado': True,
                'ya_estaba': True,
                'pendiente': False,
                'procesando': False,
                'mensaje': 'La notificación ya está registrada; no se volvió a enviar.',
            }
        else:
            notificacion = procesar_notificacion(codigo)

    return jsonify(
        ok=True,
        guardado=True,
        codigo=codigo,
        estado=registro['estado'],
        notificacion=notificacion,
    )


# Interpreta los valores afirmativos que Google Sheets puede guardar en NOTIFICADO.
def _valor_notificado(valor):
    return str(valor or '').strip().upper().replace('Í', 'I') in {
        'SI', 'S', 'YES', 'TRUE', 'NOTIFICADO'
    }


# Permite iniciar el servidor de desarrollo al ejecutar directamente este archivo.
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)