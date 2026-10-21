from datetime import datetime

from flask import Flask, render_template

from conexion_sheets import obtener_datos
from analisis import calcular_kpis
from graficos import generar_graficos

app = Flask(__name__)


@app.route('/')
def inicio():
    """Carga los datos, calcula los indicadores y muestra el dashboard."""
    error_carga = None
    df = None

    try:
        df = obtener_datos()
    except Exception:
        # El detalle técnico queda en la terminal, no se expone en la web.
        app.logger.exception('No se pudieron obtener los datos de Google Sheets.')
        error_carga = (
            'No se pudieron cargar los datos de Google Sheets. '
            'Revisa la conexión y vuelve a intentarlo.'
        )

    kpis = calcular_kpis(df)

    try:
        generar_graficos(df)
    except Exception:
        app.logger.exception('No se pudo generar el gráfico de estados.')

    # Copia segura de los datos para la tabla y ocultamiento de la columna FIRMA.
    tabla_html = ''
    if df is not None and not df.empty:
        df_tabla = df.copy()
        columnas_firma = [
            columna for columna in df_tabla.columns
            if str(columna).strip().casefold() == 'firma'
        ]
        if columnas_firma:
            df_tabla = df_tabla.drop(columns=columnas_firma)

        tabla_html = df_tabla.to_html(
            classes='table table-hover dashboard-table mb-0',
            index=False,
            border=0,
            escape=True,
        )

    return render_template(
        'dashboard.html',
        kpis=kpis,
        tabla=tabla_html,
        error_carga=error_carga,
        actualizado=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        version_grafico=int(datetime.now().timestamp()),
    )


if __name__ == '__main__':
    # Util durante el desarrollo local.
    app.run(debug=True)
