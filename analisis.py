import pandas as pd

def _buscar_columna_estado(df):
    """Encuentra la columna de estado sin depender de mayúsculas o espacios."""
    for columna in df.columns:
        normalizada = ' '.join(str(columna).strip().upper().split())
        if normalizada in ['ESTADO DE VALIDACIÓN', 'ESTADO DE VALIDACION', 'COLUMNA 1']:
            return columna
    return None

def calcular_kpis(df):
    """Calcula el total de registros y la distribución por estado."""
    if df is None or df.empty:
        return {
            'total_registros': 0,
            'conteo_estados': {},
            'registros_sin_estado': 0,
        }

    resultado = {
        'total_registros': int(len(df)),
        'conteo_estados': {},
        'registros_sin_estado': 0,
    }

    columna_estado = _buscar_columna_estado(df)
    if columna_estado is None:
        return resultado

    estados = df[columna_estado].fillna('Sin estado').astype(str).str.strip()
    estados = estados.replace('', 'Sin estado')
    conteo = estados.value_counts(dropna=False)

    resultado['conteo_estados'] = {
        str(estado): int(cantidad) for estado, cantidad in conteo.items()
    }
    resultado['registros_sin_estado'] = int((estados == 'Sin estado').sum())
    return resultado

# ======================================================================
# FUNCIONES DE FERNANDO
# ======================================================================

def contar_por_motivo_gasto(df, columna='Motivo del Gasto'):
    """
    Función 1: Usa un bucle FOR para contar cuántas solicitudes hay por cada motivo.
    """
    conteo_motivos = {}
    
    col_real = next((c for c in df.columns if 'MOTIVO' in str(c).upper()), None)
    
    if col_real:
        lista_motivos = df[col_real].fillna('No especificado').tolist()
        
        for motivo in lista_motivos:
            motivo_limpio = str(motivo).strip()
            if motivo_limpio in conteo_motivos:
                conteo_motivos[motivo_limpio] += 1
            else:
                conteo_motivos[motivo_limpio] = 1
                
    return conteo_motivos

def sumar_montos_por_area(df):
    """
    Función 2: Usa un bucle FOR para sumar el monto total declarado por cada área.
    """
    suma_por_area = {}
    
    col_area_real = None
    col_monto_real = None
    
    for col in df.columns:
        col_norm = str(col).upper()
        if 'ÁREA' in col_norm or 'AREA' in col_norm:
            col_area_real = col
        if 'MONTO' in col_norm:
            col_monto_real = col
            
    if col_area_real and col_monto_real:
        lista_areas = df[col_area_real].fillna('Sin especificar').tolist()
        lista_montos = df[col_monto_real].fillna(0).tolist()
        
        for i in range(len(lista_areas)):
            area = str(lista_areas[i]).strip()
            
            monto_str = str(lista_montos[i]).replace(',', '.')
            try:
                monto_float = float(monto_str)
            except ValueError:
                monto_float = 0.0
            
            if area in suma_por_area:
                suma_por_area[area] += monto_float
            else:
                suma_por_area[area] = monto_float
    else:
        print(f"Error: No se encontraron las columnas. Columnas actuales: {df.columns.tolist()}")
                
    return suma_por_area


# ======================================================================
# FUNCIONES DE PAOLA
# ======================================================================

def sumar_montos_por_persona(df):
    """
    Función Paola 1: Suma cuánto dinero de movilidad ha solicitado cada persona.
    """
    gastos_persona = {}
    col_nombre = next((c for c in df.columns if 'NOMBRE' in str(c).upper() or 'SOLICITANTE' in str(c).upper()), None)
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if col_nombre and col_monto:
        lista_nombres = df[col_nombre].fillna('Sin nombre').tolist()
        lista_montos = df[col_monto].fillna(0).tolist()
        
        for i in range(len(lista_nombres)):
            nombre = str(lista_nombres[i]).strip()
            if not nombre:
                nombre = 'Sin nombre'
            monto_str = str(lista_montos[i]).replace(',', '.')
            try:
                monto_float = float(monto_str)
            except ValueError:
                monto_float = 0.0
                
            if nombre in gastos_persona:
                gastos_persona[nombre] += monto_float
            else:
                gastos_persona[nombre] = monto_float
                
    return gastos_persona

def contar_solicitudes_pendientes(df):
    """
    Función Paola 2: Cuenta mediante un bucle cuántas solicitudes de movilidad faltan revisar (estado PENDIENTE).
    """
    pendientes = 0
    col_estado = _buscar_columna_estado(df)
    
    if col_estado:
        lista_estados = df[col_estado].fillna('Sin estado').tolist()
        
        for estado in lista_estados:
            if str(estado).strip().upper() == 'PENDIENTE':
                pendientes += 1
                
    return pendientes


# ======================================================================
# FUNCIONES DE ANDRÉ
# ======================================================================

def calcular_promedio_gasto_movilidad(df):
    """
    Función André 1: Calcula el costo promedio de los viajes/movilidades registradas.
    """
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if not col_monto:
        return 0.0
        
    lista_montos = df[col_monto].fillna(0).tolist()
    suma_total = 0.0
    cantidad_viajes = 0
    
    for monto in lista_montos:
        monto_str = str(monto).replace(',', '.')
        try:
            monto_float = float(monto_str)
            if monto_float > 0:
                suma_total += monto_float
                cantidad_viajes += 1
        except ValueError:
            pass
            
    if cantidad_viajes == 0:
        return 0.0
        
    return suma_total / cantidad_viajes

def contar_gastos_excesivos(df, limite=45.20):
    """
    Función André 2: Cuenta cuántos pasajes/movilidades superan el límite de la Normativa SUNAT (S/. 45.20).
    """
    excesivos = 0
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if col_monto:
        lista_montos = df[col_monto].fillna(0).tolist()
        
        for monto in lista_montos:
            monto_str = str(monto).replace(',', '.')
            try:
                monto_float = float(monto_str)
                if monto_float > limite:
                    excesivos += 1
            except ValueError:
                pass
                
    return excesivos


# ======================================================================
# BLOQUE DE PRUEBA
# ======================================================================
if __name__ == '__main__':
    from conexion_sheets import obtener_datos

    df_prueba = obtener_datos()
    
    if df_prueba is not None:
        print("\n=== RESULTADOS DE LAS FUNCIONES ===")
        print('1. Conteo por Motivo de Gasto (Fernando):')
        mis_motivos = contar_por_motivo_gasto(df_prueba)
        for motivo, cantidad in mis_motivos.items():
            print(f"   - {motivo}: {cantidad}")
            
        print('\n2. Suma de Montos por Área / Carrera (Fernando):')
        mis_montos = sumar_montos_por_area(df_prueba)
        for area, total in mis_montos.items():
            print(f"   - {area}: S/. {total:.2f}")
            
        print("\n=== RESULTADOS ===")
        print('3. Gasto de movilidad acumulado por persona (Paola):')
        gastos_pers = sumar_montos_por_persona(df_prueba)
        for pers, tot in gastos_pers.items():
            print(f"   - {pers}: S/. {tot:.2f}")
            
        print('\n4. Solicitudes de movilidad pendientes de revisión (Paola):')
        pendientes = contar_solicitudes_pendientes(df_prueba)
        print(f"   - Total pendientes: {pendientes}")

        print("\n=== RESULTADOS ===")
        print('5. Costo promedio por movilidad (André):')
        promedio = calcular_promedio_gasto_movilidad(df_prueba)
        print(f"   - Promedio: S/. {promedio:.2f}")
        
        print('\n6. Alertas SUNAT: Movilidades que superan el límite de S/. 45.20 (André):')
        excesivos = contar_gastos_excesivos(df_prueba, limite=45.20)
        print(f"   - Registro(s) que exceden los S/. 45.20: {excesivos}")
        
        print("\n----------------------------------------")