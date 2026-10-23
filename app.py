from datetime import datetime

from flask import Flask, render_template

from conexion_sheets import obtener_datos
from analisis import calcular_kpis
# AÑADIMOS LA IMPORTACIÓN DE LA NUEVA FUNCIÓN
from graficos import colores_para_estados, generar_graficos, grafico_estados_interactivo 

app = Flask(__name__)


@app.route('/')
def inicio():
    """Carga los datos, calcula los indicadores y muestra el dashboard."""
    error_carga = None
    df = None
    grafico_html = "" # Variable nueva para Plotly

    try:
        df = obtener_datos()
    except Exception:
        app.logger.exception('No se pudieron obtener los datos de Google Sheets.')
        error_carga = (
            'No se pudieron cargar los datos de Google Sheets. '
            'Revisa la conexión y vuelve a intentarlo.'
        )

    kpis = calcular_kpis(df)
    colores_estados = colores_para_estados(kpis['conteo_estados'].keys())

    try:
        # Mantenemos la generación del PNG estático para no romper nada
        generar_graficos(df)
        
        # AÑADIDO: Generamos el gráfico interactivo si hay datos
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
        grafico_interactivo=grafico_html,  # Enviamos Plotly al HTML
        colores_estados=colores_estados,
    )


if __name__ == '__main__':
    app.run(debug=True)