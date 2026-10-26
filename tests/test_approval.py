import unittest
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import pandas as pd
import requests

import app as dashboard
from apps_script_client import ErrorAppsScript, TOKEN_VARIABLE, _configuracion, procesar_notificacion
from configuracion import cargar_configuracion
from conexion_sheets import (
    ErrorRegistro,
    aprobar_registro,
    actualizar_estado_registro,
    marcar_registro_notificado,
)


# Encabezados y registros de ejemplo reutilizados por las pruebas con Google Sheets simulado.
HEADERS = [
    'CÓDIGO',
    'Nombres y apellidos',
    'Correo electrónico',
    'Monto declarado',
    'CONTROL DE LEY',
    'ESTADO DE VALIDACIÓN',
    'NOTIFICADO',
    'Firma',
    'Fórmula auxiliar',
]


def filas_hoja(estado='PENDIENTE', control='Dentro del límite', monto='40.00'):
    return [
        HEADERS,
        ['VG-001', 'Ana Pérez', 'ana@example.test', monto, control, estado, 'No', '', '=SUM(1,1)'],
    ]


# Comprueba validaciones y escrituras de estados en la capa de acceso a Sheets.
class ApprovalSheetTests(unittest.TestCase):
    # Las pruebas verifican que solo se cambie la celda correcta y que se respeten las reglas.
    def test_approval_updates_only_status_cell_by_unique_code(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [filas_hoja(), filas_hoja(estado='APROBADO')]

        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = aprobar_registro('VG-001', 45.20)

        hoja.update_cell.assert_called_once_with(2, 6, 'APROBADO')
        self.assertEqual(resultado['codigo'], 'VG-001')
        self.assertEqual(resultado['nombre'], 'Ana Pérez')
        self.assertEqual(resultado['correo'], 'ana@example.test')

    def test_approval_uses_current_limit_parameter(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(monto='50.00'), filas_hoja(estado='APROBADO', monto='50.00')
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            aprobar_registro('VG-001', 55)
        hoja.update_cell.assert_called_once_with(2, 6, 'APROBADO')

    def test_approved_and_discarded_records_cannot_be_approved_again(self):
        for estado in ('APROBADO', 'DESCARTADO'):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(estado=estado)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    aprobar_registro('VG-001', 45.20)
            hoja.update_cell.assert_not_called()

    def test_control_and_limit_restrictions_are_checked_before_write(self):
        for control, monto in (
            ('Excede el límite', '40.00'),
            ('Dentro del límite', '50.00'),
            ('Dentro del límite', '0'),
            ('Dentro del límite', '-1'),
        ):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(control=control, monto=monto)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    aprobar_registro('VG-001', 45.20)
            hoja.update_cell.assert_not_called()

    def test_duplicate_code_is_rejected(self):
        hoja = Mock()
        hoja.get_all_values.return_value = filas_hoja() + [
            ['VG-001', 'Otra persona', 'otra@example.test', '20', 'Dentro del límite', 'PENDIENTE', 'No', '', '=1'],
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            with self.assertRaises(ErrorRegistro):
                aprobar_registro('VG-001', 45.20)
        hoja.update_cell.assert_not_called()

    def test_notification_flag_is_written_only_after_send_confirmation(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(estado='APROBADO'),
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = marcar_registro_notificado('VG-001')
        self.assertTrue(resultado)
        hoja.update_cell.assert_called_once_with(2, 7, 'SÍ')

    def test_repeated_approval_is_rejected_after_first_write(self):
        class HojaEnMemoria:
            def __init__(self):
                self.valores = filas_hoja()
                self.actualizaciones = []

            def get_all_values(self):
                return self.valores

            def update_cell(self, fila, columna, valor):
                self.actualizaciones.append((fila, columna, valor))
                self.valores[fila - 1][columna - 1] = valor

        hoja = HojaEnMemoria()
        with patch('conexion_sheets.conectar', return_value=hoja):
            aprobar_registro('VG-001', 45.20)
            with self.assertRaises(ErrorRegistro):
                aprobar_registro('VG-001', 45.20)
        self.assertEqual(hoja.actualizaciones, [(2, 6, 'APROBADO')])

    def test_pending_record_can_be_rejected_by_unique_code(self):
        hoja = Mock()
        hoja.get_all_values.side_effect = [
            filas_hoja(control='Excede el límite', monto='50'),
            filas_hoja(estado='DESCARTADO', control='Excede el límite', monto='50'),
        ]
        with patch('conexion_sheets.conectar', return_value=hoja):
            resultado = actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
        hoja.update_cell.assert_called_once_with(2, 6, 'DESCARTADO')
        self.assertEqual(resultado['estado'], 'DESCARTADO')

    def test_rejection_cannot_be_repeated_or_apply_to_non_pending_record(self):
        for estado in ('APROBADO', 'DESCARTADO'):
            hoja = Mock()
            hoja.get_all_values.return_value = filas_hoja(estado=estado)
            with patch('conexion_sheets.conectar', return_value=hoja):
                with self.assertRaises(ErrorRegistro):
                    actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
            hoja.update_cell.assert_not_called()

    def test_sheet_write_failure_leaves_previous_status_untouched(self):
        class HojaEnMemoria:
            def __init__(self):
                self.valores = filas_hoja()

            def get_all_values(self):
                return self.valores

            def update_cell(self, fila, columna, valor):
                raise RuntimeError('Sheets API unavailable')

        hoja = HojaEnMemoria()
        with patch('conexion_sheets.conectar', return_value=hoja):
            with self.assertRaises(RuntimeError):
                actualizar_estado_registro('VG-001', 'DESCARTADO', 45.20)
        self.assertEqual(hoja.valores[1][5], 'PENDIENTE')


# Prueba endpoints Flask, protección CSRF y coordinación con el servicio de notificaciones.
class ApprovalApiTests(unittest.TestCase):
    # Cada caso usa un cliente de prueba y sustituye dependencias externas por mocks.
    def setUp(self):
        dashboard.app.config.update(TESTING=True)
        self.client = dashboard.app.test_client()
        self.data = pd.DataFrame([{
            'CÓDIGO': 'VG-001',
            'Nombres y apellidos': 'Ana Pérez',
            'Correo electrónico': 'ana@example.test',
            'Monto declarado': 40.0,
            'CONTROL DE LEY': 'Dentro del límite',
            'ESTADO DE VALIDACIÓN': 'PENDIENTE',
            'NOTIFICADO': 'No',
            'Firma': '',
        }])
        with patch.multiple(
            dashboard,
            obtener_datos=Mock(return_value=self.data),
            generar_graficos=Mock(),
            grafico_estados_interactivo=Mock(return_value=Mock(to_html=Mock(return_value=''))),
        ):
            response = self.client.get('/')
            self.dashboard_html = response.get_data(as_text=True)
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def post_approval(self):
        return self.client.post(
            '/api/registros/aprobar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )

    def post_rejection(self):
        return self.client.post(
            '/api/registros/rechazar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )

    def test_dashboard_renders_both_actions_without_extra_key(self):
        self.assertIn('id="aprobarRegistro"', self.dashboard_html)
        self.assertIn('id="rechazarRegistro"', self.dashboard_html)
        self.assertGreater(
            self.dashboard_html.index('id="modalDetalleRegistro"'),
            self.dashboard_html.index('</main>'),
        )
        self.assertIn('¿Deseas ${verbo} este registro?', self.dashboard_html)
        self.assertIn('Sí, ${verbo}', self.dashboard_html)
        self.assertIn('if (!confirmacion.isConfirmed)', self.dashboard_html)
        self.assertLess(
            self.dashboard_html.index('if (!confirmacion.isConfirmed)'),
            self.dashboard_html.index('const response = await fetch(`/api/registros/${accion}`'),
        )
        self.assertIn('aprobacionesEnCurso.has(codigo)', self.dashboard_html)
        self.assertIn('/api/registros/notificacion/reintentar', self.dashboard_html)
        self.assertIn('El registro fue actualizado, pero no se pudo enviar la notificación', self.dashboard_html)
        self.assertIn('function renderFirma', self.dashboard_html)
        self.assertNotIn('Clave de aprobación', self.dashboard_html)
        self.assertNotIn('input: \'password\'', self.dashboard_html)

    @patch('app.procesar_notificacion', return_value={
        'enviado': True, 'registrado': True, 'ya_estaba': False,
        'pendiente': False, 'procesando': False,
    })
    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'APROBADO',
    })
    def test_api_requests_apps_script_only_after_persisted_approval(self, approve, process):
        response = self.post_approval()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['guardado'])
        self.assertTrue(response.json['aprobado'])
        approve.assert_called_once_with('VG-001', 'APROBADO', dashboard.LIMITE_GASTO)
        process.assert_called_once_with('VG-001')

    @patch('app.procesar_notificacion', return_value={
        'enviado': False, 'registrado': False, 'ya_estaba': False,
        'pendiente': True, 'procesando': False,
        'mensaje': 'Apps Script no está configurado.',
        'error': 'Apps Script no está configurado.',
    })
    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'APROBADO',
    })
    def test_notification_failure_keeps_saved_state_and_reports_pending_mail(self, approve, process):
        response = self.post_approval()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['aprobado'])
        self.assertFalse(response.json['notificacion']['enviado'])
        self.assertTrue(response.json['guardado'])
        process.assert_called_once_with('VG-001')

    @patch('app.actualizar_estado_registro', side_effect=ErrorRegistro('Ya no está pendiente.', 409))
    @patch('app.procesar_notificacion')
    def test_failed_approval_never_calls_apps_script(self, process, approve):
        response = self.post_approval()
        self.assertEqual(response.status_code, 409)
        process.assert_not_called()


    @patch('app.obtener_registro_por_codigo', return_value={'estado': 'PENDIENTE'})
    @patch('app.actualizar_estado_registro', side_effect=RuntimeError('Sheets unavailable'))
    @patch('app.procesar_notificacion')
    def test_sheet_write_failure_returns_error_without_notification(self, process, update, lookup):
        response = self.post_rejection()
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json['ok'])
        process.assert_not_called()
        update.assert_called_once_with('VG-001', 'DESCARTADO', dashboard.LIMITE_GASTO)

    @patch('app.procesar_notificacion', return_value={
        'enviado': True, 'registrado': True, 'ya_estaba': False,
        'pendiente': False, 'procesando': False,
    })
    @patch('app.obtener_registro_por_codigo', return_value={
        'codigo': 'VG-001', 'estado': 'APROBADO', 'notificado': 'No',
        'tiene_columna_notificado': True,
    })
    @patch('app.actualizar_estado_registro', side_effect=TimeoutError('response timed out'))
    def test_write_timeout_is_read_back_before_requesting_notification(self, update, lookup, process):
        response = self.post_approval()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['guardado'])
        lookup.assert_called_once_with('VG-001')
        process.assert_called_once_with('VG-001')

    def test_missing_csrf_token_is_rejected(self):
        response = self.client.post('/api/registros/aprobar', json={'codigo': 'VG-001'})
        self.assertEqual(response.status_code, 403)

    @patch('app.actualizar_estado_registro', return_value={
        'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
        'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
        'estado': 'DESCARTADO',
    })
    def test_rejection_persists_discarded_and_notifies_once(self, update):
        with patch('app.procesar_notificacion', return_value={
            'enviado': True, 'registrado': True, 'ya_estaba': False,
            'pendiente': False, 'procesando': False,
        }) as process:
            response = self.post_rejection()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['estado'], 'DESCARTADO')
        self.assertTrue(response.json['rechazado'])
        update.assert_called_once_with('VG-001', 'DESCARTADO', dashboard.LIMITE_GASTO)
        process.assert_called_once_with('VG-001')

    @patch('app.procesar_notificacion', return_value={
        'enviado': True, 'registrado': True, 'ya_estaba': False,
        'pendiente': False, 'procesando': False,
    })
    @patch('app.actualizar_estado_registro', side_effect=[
        {
            'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
            'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
            'estado': 'APROBADO',
        },
        ErrorRegistro('Solo se pueden aprobar registros que continúan pendientes.', 409),
    ])
    def test_repeated_api_request_cannot_process_duplicate_notification(self, approve, process):
        primera = self.post_approval()
        segunda = self.post_approval()
        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 409)
        process.assert_called_once_with('VG-001')

    @patch('app.procesar_notificacion', return_value={
        'enviado': False, 'registrado': False, 'ya_estaba': False,
        'pendiente': True, 'procesando': False,
    })
    @patch('app.obtener_registro_por_codigo', return_value={
        'codigo': 'VG-001', 'estado': 'APROBADO', 'notificado': 'No',
        'tiene_columna_notificado': True,
    })
    def test_retry_processes_pending_notification_without_rewriting_state(self, lookup, process):
        response = self.client.post(
            '/api/registros/notificacion/reintentar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['guardado'])
        self.assertEqual(response.json['estado'], 'APROBADO')
        lookup.assert_called_once_with('VG-001')
        process.assert_called_once_with('VG-001')

    @patch('app.procesar_notificacion')
    @patch('app.obtener_registro_por_codigo', return_value={
        'codigo': 'VG-001', 'estado': 'DESCARTADO', 'notificado': 'SÍ',
        'tiene_columna_notificado': True,
    })
    def test_retry_does_not_resend_already_notified_record(self, lookup, process):
        response = self.client.post(
            '/api/registros/notificacion/reintentar',
            json={'codigo': 'VG-001'},
            headers={'X-CSRF-Token': self.csrf},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['notificacion']['ya_estaba'])
        process.assert_not_called()

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test-deployment/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'test-only-secret',
    })
    @patch('apps_script_client.requests.post')
    @patch('app.actualizar_estado_registro')
    def test_controlled_api_to_apps_script_flow_uses_exec_after_sheet_write(self, update, post):
        eventos = []

        def guardar(*args):
            eventos.append('sheets')
            return {
                'codigo': 'VG-001', 'nombre': 'Ana Pérez', 'correo': 'ana@example.test',
                'monto': '40.00', 'notificado': 'No', 'tiene_columna_notificado': True,
                'estado': 'APROBADO',
            }

        update.side_effect = guardar
        respuesta_remota = Mock(status_code=200, ok=True)
        respuesta_remota.json.return_value = {
            'ok': True, 'estado_guardado': True, 'estado_final': True,
            'notificado': True, 'notificacion_enviada': True,
            'estado_notificado': 'SÍ', 'mensaje': 'Notificación enviada y registrada.',
        }

        def llamada_http(*args, **kwargs):
            eventos.append('apps_script')
            return respuesta_remota

        post.side_effect = llamada_http
        response = self.post_approval()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['guardado'])
        self.assertTrue(response.json['notificacion']['enviado'])
        self.assertEqual(eventos, ['sheets', 'apps_script'])
        self.assertEqual(
            post.call_args.args[0],
            'https://script.google.com/macros/s/test-deployment/exec',
        )
        self.assertEqual(post.call_args.kwargs['json']['accion'], 'procesar')
        self.assertEqual(post.call_args.kwargs['json']['codigo'], 'VG-001')


# Verifica carga de configuración y condiciones de seguridad de la integración remota.
class ConfigurationTests(unittest.TestCase):
    def test_apps_script_client_uses_only_the_canonical_shared_secret(self):
        self.assertEqual(TOKEN_VARIABLE, 'APPS_SCRIPT_SHARED_SECRET')
        environment = {
            'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
            'APPS_SCRIPT_SHARED_SECRET': '',
            'APPS_SCRIPT_TOKEN': 'must-not-be-used',
            'PYTHON_WEBHOOK_TOKEN': 'must-not-be-used-either',
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(ErrorAppsScript) as error:
                _configuracion()
        self.assertEqual(error.exception.categoria, 'configuracion_secreto_ausente')

    def test_project_env_is_loaded_without_overriding_process_environment(self):
        with tempfile.TemporaryDirectory() as directorio:
            archivo_env = Path(directorio) / '.env'
            archivo_env.write_text(
                'APPS_SCRIPT_WEB_APP_URL="https://script.google.com/macros/s/id/exec"\n'
                'APPS_SCRIPT_SHARED_SECRET=local-test-token # comentario\n',
                encoding='utf-8',
            )
            with patch.dict(os.environ, {'APPS_SCRIPT_SHARED_SECRET': 'process-token'}, clear=True):
                self.assertTrue(cargar_configuracion(archivo_env))
                self.assertEqual(
                    os.environ['APPS_SCRIPT_WEB_APP_URL'],
                    'https://script.google.com/macros/s/id/exec',
                )
                self.assertEqual(os.environ['APPS_SCRIPT_SHARED_SECRET'], 'process-token')


# Comprueba el contrato HTTP con Apps Script y el manejo de errores y tiempos de espera.
class AppsScriptClientTests(unittest.TestCase):
    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_success_response_distinguishes_sent_and_persisted(self, post):
        respuesta = Mock()
        respuesta.json.return_value = {
            'ok': True, 'estado_guardado': True, 'estado_final': True, 'notificado': True,
            'notificacion_enviada': True, 'estado_notificado': 'SÍ',
        }
        post.return_value = respuesta
        resultado = procesar_notificacion('VG-001')
        self.assertTrue(resultado['enviado'])
        self.assertTrue(resultado['registrado'])
        self.assertFalse(resultado['pendiente'])
        self.assertEqual(post.call_args.kwargs['json']['codigo'], 'VG-001')
        self.assertEqual(post.call_args.kwargs['json']['accion'], 'procesar')

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_apps_script_error_preserves_pending_notification_result(self, post):
        respuesta = Mock()
        respuesta.json.return_value = {
            'ok': False, 'estado_guardado': True, 'estado_final': True,
            'notificado': False, 'notificacion_enviada': False,
            'estado_notificado': 'ERROR', 'error': 'MailApp send failure',
        }
        post.return_value = respuesta
        resultado = procesar_notificacion('VG-001')
        self.assertTrue(resultado['estado_guardado'])
        self.assertFalse(resultado['enviado'])
        self.assertTrue(resultado['pendiente'])
        self.assertEqual(resultado['estado'], 'ERROR')
        self.assertEqual(resultado['error'], 'MailApp send failure')

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_timeout_checks_persisted_result_without_repeating_delivery(self, post):
        confirmacion = Mock()
        confirmacion.json.return_value = {
            'ok': True, 'estado_guardado': True, 'estado_final': True, 'notificado': True,
            'notificacion_enviada': False, 'ya_estaba_notificado': True,
            'procesando': False, 'estado_notificado': 'SÍ',
        }
        post.side_effect = [requests.Timeout(), confirmacion]
        resultado = procesar_notificacion('VG-001')
        self.assertTrue(resultado['ya_estaba'])
        self.assertTrue(resultado['registrado'])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs['json']['accion'], 'procesar')
        self.assertEqual(post.call_args_list[1].kwargs['json']['accion'], 'consultar')

    @patch.dict(os.environ, {}, clear=True)
    @patch('apps_script_client.requests.post')
    def test_missing_server_configuration_reports_pending_notification(self, post):
        resultado = procesar_notificacion('VG-001')
        self.assertFalse(resultado['enviado'])
        self.assertTrue(resultado['pendiente'])
        self.assertIn('Falta la URL', resultado['mensaje'])
        post.assert_not_called()

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_authentication_failure_is_classified_without_exposing_token(self, post):
        respuesta = Mock(status_code=200, ok=True)
        respuesta.json.return_value = {'ok': False, 'error': 'No autorizado.'}
        post.return_value = respuesta
        resultado = procesar_notificacion('VG-001')
        self.assertEqual(resultado['error_categoria'], 'autenticacion_rechazada')
        self.assertIn('rechazó la autenticación', resultado['mensaje'])
        self.assertNotIn('server-only-test-secret', resultado['mensaje'])

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://script.google.com/macros/s/test/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_html_response_identifies_missing_or_old_dopost_deployment(self, post):
        respuesta = Mock(status_code=200, ok=True)
        respuesta.json.side_effect = ValueError('not JSON')
        post.return_value = respuesta
        resultado = procesar_notificacion('VG-001')
        self.assertEqual(resultado['error_categoria'], 'respuesta_invalida_sin_dopost')
        self.assertIn('doGet', resultado['mensaje'])

    @patch.dict(os.environ, {
        'APPS_SCRIPT_WEB_APP_URL': 'https://example.com/exec',
        'APPS_SCRIPT_SHARED_SECRET': 'server-only-test-secret',
    })
    @patch('apps_script_client.requests.post')
    def test_non_apps_script_url_is_rejected_before_http_request(self, post):
        resultado = procesar_notificacion('VG-001')
        self.assertEqual(resultado['error_categoria'], 'configuracion_url_invalida')
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
