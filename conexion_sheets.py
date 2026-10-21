import gspread
import pandas as pd

# ID de la hoja de Google Sheets (¡Este es el ID correcto de tu navegador!)
SPREADSHEET_ID = '1beuJk14LuFMRLU3yOCdeYLjaWf_jhaIbePCFUTbW6NE'

def obtener_datos():
    """
    Se conecta a Google Sheets usando credenciales.json 
    y retorna los datos de la primera hoja como un DataFrame de Pandas.
    """
    try:
        # Autenticación con el archivo credenciales.json
        cliente = gspread.service_account(filename='credenciales.json')
        
        # Abrir el libro de cálculo por su ID
        archivo = cliente.open_by_key(SPREADSHEET_ID)
        
        # Seleccionar la primera pestaña/hoja del documento
        hoja = archivo.sheet1
        
        valores = hoja.get_all_values()
        
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
        cliente_prueba = gspread.service_account(filename="credenciales.json")
        archivo_prueba = cliente_prueba.open_by_key(SPREADSHEET_ID)
        
        print("\n¡Conexión exitosa!")
        print(f"Título de la hoja: {archivo_prueba.title}")
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