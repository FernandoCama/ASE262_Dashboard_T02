from decimal import Decimal, InvalidOperation
from pathlib import Path

import gspread
import pandas as pd

# ID de la hoja de Google Sheets (¡Este es el ID correcto de tu navegador!)
SPREADSHEET_ID = '1beuJk14LuFMRLU3yOCdeYLjaWf_jhaIbePCFUTbW6NE'
RUTA_CREDENCIALES = Path(__file__).resolve().parent / 'credenciales.json'


def conectar():
    """Abre la primera pestaña de la hoja usando la cuenta de servicio."""
    cliente = gspread.service_account(filename=str(RUTA_CREDENCIALES))
    archivo = cliente.open_by_key(SPREADSHEET_ID)
    return archivo.sheet1


def _leer_valores():
    """Lee las filas de la pestaña, incluido el encabezado."""
    return conectar().get_all_values()


def leer_todos():
    """Devuelve las filas de gastos sin incluir el encabezado."""
    valores = _leer_valores()
    return valores[1:] if valores else []


def agregar_gasto(fecha, correo, nombre, dni, area, motivo, monto, codigo,
                  control_ley, estado, notificado):
    """Valida y agrega un gasto al final de la hoja; propaga errores de Sheets."""
    campos = [
        fecha, correo, nombre, dni, area, motivo, monto, codigo,
        control_ley, estado, notificado,
    ]
    if any(valor is None or not str(valor).strip() for valor in campos):
        raise ValueError('Todos los campos del gasto son obligatorios.')

    try:
        monto_decimal = Decimal(str(monto).strip().replace(',', '.'))
    except InvalidOperation as error:
        raise ValueError('El monto debe ser un número válido.') from error
    if not monto_decimal.is_finite() or monto_decimal < 0:
        raise ValueError('El monto debe ser un número finito y no negativo.')

    fila = [str(valor).strip() for valor in campos]
    fila[6] = float(monto_decimal)

    hoja = conectar()
    encabezados = hoja.row_values(1)
    if len(encabezados) != len(fila):
        raise ValueError(
            f'La hoja tiene {len(encabezados)} columnas; se esperaban {len(fila)}.'
        )

    resultado = hoja.append_row(fila, value_input_option='USER_ENTERED')
    print(f"Gasto {fila[7]} registrado")
    return resultado


def obtener_datos():
    """
    Se conecta a Google Sheets usando credenciales.json 
    y retorna los datos de la primera hoja como un DataFrame de Pandas.
    """
    try:
        valores = _leer_valores()
        
        if not valores:
            return None
            
        # Construimos el DataFrame con los valores
        encabezados = valores[0]
        df = pd.DataFrame(valores[1:], columns=encabezados)
        
        # LIMPIEZA 1: Si existe la columna de fecha
        if 'FECHA Y HORA' in df.columns:
             df['FECHA Y HORA'] = df['FECHA Y HORA'].astype(str).str.replace("'", "", regex=False)

        # LIMPIEZA 2: Convertir la columna de Monto respetando los decimales reales
        for col in df.columns:
            if 'MONTO' in str(col).upper():
                # Reemplaza la coma por punto y lo convierte a número flotante real
                df[col] = df[col].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0.0)

        return df

    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        return None

# Bloque de prueba de conexión
if __name__ == "__main__":
    print("Conectando a Google Sheets...")
    
    # Autenticamos y verificamos la conexión
    try:
        hoja_prueba = conectar()
        
        print("\n¡Conexión exitosa!")
        print(f"Nombre de la pestaña: {hoja_prueba.title}")
    except Exception as e:
        print(f"Error al obtener el título: {e}")

    # Llamamos a la función que trae y limpia los datos
    df_datos = obtener_datos()
    
    if df_datos is not None and not df_datos.empty:
        print(f"Datos recuperados correctamente. Total de filas procesadas: {len(df_datos)}")
        print("\nPrimeras filas del DataFrame:")
        print(df_datos.head())
    else:
        print("\nNo se pudieron cargar los datos o la hoja está vacía.")