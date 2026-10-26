"""Load the dashboard's optional .env before application initialization."""

import os
from pathlib import Path
import re


_NOMBRE_VARIABLE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


# Lee el archivo de entorno elegido y agrega variables sin sobrescribir las ya existentes.
def cargar_configuracion(ruta=None):
    """Load KEY=VALUE lines, preserving variables already set by the process.

    DASHBOARD_ENV_FILE can point to an external, untracked config file. When
    omitted, the project-root .env is used, matching the usual `python app.py`
    startup command without requiring a CLI-specific dotenv loader.
    """
    if ruta is None:
        configuracion_externa = os.environ.get('DASHBOARD_ENV_FILE', '').strip()
        ruta = Path(configuracion_externa) if configuracion_externa else Path(__file__).resolve().parent / '.env'
    else:
        ruta = Path(ruta)

    if not ruta.is_file():
        return False

    for linea in ruta.read_text(encoding='utf-8-sig').splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#'):
            continue
        if linea.startswith('export '):
            linea = linea[7:].lstrip()
        nombre, separador, valor = linea.partition('=')
        nombre = nombre.strip()
        if not separador or not _NOMBRE_VARIABLE.fullmatch(nombre):
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {'"', "'"}:
            valor = valor[1:-1]
        elif ' #' in valor:
            valor = valor.split(' #', 1)[0].rstrip()
        os.environ.setdefault(nombre, valor)
    return True