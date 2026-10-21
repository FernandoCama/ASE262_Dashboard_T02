from pathlib import Path
import unicodedata

import matplotlib
matplotlib.use('Agg')  # Genera la imagen sin abrir una ventana gráfica.
import matplotlib.pyplot as plt


CARPETA_STATIC = Path(__file__).resolve().parent / 'static'
RUTA_GRAFICO = CARPETA_STATIC / 'grafico_estados.png'


def _normalizar_texto(valor):
    """Normaliza un texto para comparar nombres de columnas con seguridad."""
    texto = ' '.join(str(valor).strip().upper().split())
    return ''.join(
        caracter for caracter in unicodedata.normalize('NFD', texto)
        if unicodedata.category(caracter) != 'Mn'
    )


def _buscar_columna_estado(df):
    """Encuentra la columna de validación aunque cambien acentos o espacios."""
    if df is None or df.empty:
        return None

    for columna in df.columns:
        if _normalizar_texto(columna) == 'ESTADO DE VALIDACION':
            return columna
    return None


def generar_graficos(df):
    """Genera un gráfico de barras con cantidades y porcentajes por estado."""
    CARPETA_STATIC.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=160)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')

    columna_estado = _buscar_columna_estado(df)
    if columna_estado is None:
        ax.axis('off')
        if df is None or df.empty:
            mensaje = 'No hay datos disponibles'
        else:
            mensaje = 'No se encontró la columna\nESTADO DE VALIDACIÓN'
        ax.text(0.5, 0.5, mensaje, ha='center', va='center',
                color='#64748b', fontsize=12, transform=ax.transAxes)
    else:
        estados = df[columna_estado].fillna('Sin estado').astype(str).str.strip()
        estados = estados.replace('', 'Sin estado')
        conteo = estados.value_counts()
        total_registros = int(conteo.sum())

        if conteo.empty or total_registros == 0:
            ax.axis('off')
            ax.text(0.5, 0.5, 'No hay estados para mostrar', ha='center',
                    va='center', color='#64748b', fontsize=12,
                    transform=ax.transAxes)
        else:
            # Paleta ; se repite si la hoja tiene más de tres estados.
            colores_base = ['#2ecc71', '#e74c3c', '#f39c12', '#3157d5',
                            '#14b8a6', '#8b5cf6', '#0ea5e9']
            colores = [colores_base[i % len(colores_base)]
                       for i in range(len(conteo))]

            barras = ax.bar(
                conteo.index.astype(str),
                conteo.values,
                color=colores,
                width=0.58,
                edgecolor='none',
                zorder=3,
            )

            ax.set_title('Estado de las solicitudes', fontsize=14,
                         pad=16, fontweight='bold', color='#17233c')
            ax.set_xlabel('Estado', fontsize=10, color='#64748b', labelpad=10)
            ax.set_ylabel('Cantidad', fontsize=10, color='#64748b', labelpad=8)
            ax.tick_params(axis='x', labelsize=9, colors='#475569', length=0, pad=8)
            ax.tick_params(axis='y', labelsize=9, colors='#64748b', length=0)
            plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

            # Cantidad y porcentaje encima de cada barra.
            for barra in barras:
                altura = int(barra.get_height())
                porcentaje = (altura / total_registros) * 100
                texto = f'{altura}\n({porcentaje:.1f}%)'
                ax.annotate(
                    texto,
                    xy=(barra.get_x() + barra.get_width() / 2, altura),
                    xytext=(0, 5),
                    textcoords='offset points',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                    fontweight='bold',
                    color='#334155',
                )

            # Limpiar bordes y agregar una cuadrícula discreta.
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(False)
            ax.spines['bottom'].set_color('#dbe2ec')
            ax.grid(axis='y', linestyle='--', linewidth=0.7,
                    color='#cbd5e1', alpha=0.55, zorder=0)
            ax.set_axisbelow(True)
            ax.set_ylim(0, max(conteo.values) * 1.28)

    fig.tight_layout()
    fig.savefig(RUTA_GRAFICO, dpi=180, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    return str(RUTA_GRAFICO)
