// ============================================================================
// CONFIGURACIÓN GLOBAL
// ============================================================================
var ID_LOGO = '1_6Cc0sQnmZZ8c0YgpGpbS9ME6zdQtd5I';
var ID_FIRMA_JEFE = '1_ChZv0Niw4o5ilCo3D2CY2WXQnLCbKb4'; // NUEVA FIRMA JEFE
var ID_FIRMA_ADMIN = '12zFeBQtpvD-fHRYVALO2FpTFCpU_SARv'; // NUEVA FIRMA ADMIN
var ID_SPREADSHEET = '1beuJk14LuFMRLU3yOCdeYLjaWf_jhaIbePCFUTbW6NE';
var IMAGEN_VACIA_BASE64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

// Construye el bloque de firma institucional que acompaña los correos.
function obtenerFirmaInstitucional() {
  var urlLogo = "https://drive.google.com/thumbnail?id=" + ID_LOGO + "&sz=w200";
  return "<br><br><table style='font-family: Arial, sans-serif; border-collapse: collapse; margin-top: 15px;'><tr><td style='padding-right: 15px; border-right: 2px solid #003366; vertical-align: middle;'><img src='" + urlLogo + "' alt='Valle Grande' style='width: 75px; display: block;'></td><td style='padding-left: 15px; vertical-align: middle; line-height: 1.4;'><span style='color: #003366; font-size: 14px; font-weight: bold; letter-spacing: 0.5px;'>ADMINISTRACIÓN PROSIP</span><br><span style='color: #003366; font-size: 14px; font-weight: bold; letter-spacing: 0.5px;'>I.E.S. VALLE GRANDE</span><br><span style='color: #777777; font-size: 12px;'>Gestión de Gastos por Movilidad</span></td></tr></table>";
}

// Genera un correlativo consecutivo REC- de seis dígitos según los códigos existentes.
function generarNuevoCorrelativo(hoja) {
  var ultimaFila = hoja.getLastRow();
  if (ultimaFila < 2) return "REC-000001";
  
  var codigos = hoja.getRange(2, 9, ultimaFila - 1, 1).getValues();
  var maxNum = 0;
  for (var i = 0; i < codigos.length; i++) {
    var val = codigos[i][0] ? String(codigos[i][0]).trim() : "";
    if (val.indexOf("REC-") === 0) {
      var num = parseInt(val.replace("REC-", ""), 10);
      if (!isNaN(num) && num > maxNum) maxNum = num;
    }
  }
  return "REC-" + ("000000" + (maxNum + 1)).slice(-6);
}

// Aplica alineación y bordes a la nueva fila; un fallo visual no detiene el registro.
function aplicarFormatoFila(hoja, fila) {
  try {
    hoja.getRange(fila, 1, 1, 12)
      .setHorizontalAlignment("center")
      .setVerticalAlignment("middle")
      .setBorder(true, true, true, true, true, true);
  } catch(e) {
    console.error("Error visual ignorado: " + e.message);
  }
}

// ============================================================================
// FUNCIONES AUXILIARES PARA EXTRAER E INSERTAR FIRMAS EN DOCS
// ============================================================================
// Convierte una firma Base64 o una URL de Drive en un archivo de imagen utilizable.
function obtenerBlobDeFirma(firmaDato) {
  try {
    if (!firmaDato || firmaDato === IMAGEN_VACIA_BASE64) return null;
    
    if (firmaDato.indexOf("data:image") !== -1) {
      var base64Data = firmaDato.split(",")[1];
      return Utilities.newBlob(Utilities.base64Decode(base64Data), "image/png", "firma_usuario.png");
    } 
    
    var idFirma = "";
    if (firmaDato.indexOf("id=") !== -1) {
      idFirma = firmaDato.split("id=")[1].split("&")[0];
    } else if (firmaDato.indexOf("/d/") !== -1) {
      idFirma = firmaDato.split("/d/")[1].split("/")[0];
    }
    
    if (idFirma) {
      return DriveApp.getFileById(idFirma).getBlob();
    }
  } catch (e) {
    console.error("No se pudo extraer la firma del usuario: " + e.message);
  }
  return null;
}

// Reemplaza un marcador del documento por una imagen o elimina el marcador vacío.
function insertarImagenEnDoc(body, placeholderRegex, blobImagen) {
  var elementoEncontrado = body.findText(placeholderRegex);
  if (elementoEncontrado) {
    var elementoTexto = elementoEncontrado.getElement();
    var parrafo = elementoTexto.getParent().asParagraph();
    
    if (blobImagen) {
      parrafo.clear(); 
      var img = parrafo.appendInlineImage(blobImagen);
      img.setWidth(120);
      img.setHeight(60);
      parrafo.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    } else {
      var textoLimpio = placeholderRegex.replace(/\\/g, '');
      elementoTexto.setText(elementoTexto.getText().replace(textoLimpio, ""));
    }
  }
}

// ============================================================================
// PUERTA 1: ENTRADA DESDE LA PÁGINA WEB HTML
// ============================================================================
// Sirve la interfaz de captura HTML del proyecto Apps Script.
function doGet() {
  return HtmlService.createHtmlOutputFromFile('formulario')
    .setTitle('Registro de Gastos por Movilidad')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// Devuelve objetos como respuestas HTTP JSON para el cliente Python.
function jsonRespuesta(datos) {
  return ContentService.createTextOutput(JSON.stringify(datos))
    .setMimeType(ContentService.MimeType.JSON);
}

// Compara secretos sin terminar la comparación al encontrar una diferencia temprana.
function compararSecreto(a, b) {
  a = String(a || '');
  b = String(b || '');
  if (!a || a.length !== b.length) return false;
  var diferencia = 0;
  for (var i = 0; i < a.length; i++) diferencia |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diferencia === 0;
}

// Abre la hoja configurada por propiedades del script o usa la hoja predeterminada.
function obtenerHojaConfigurada() {
  var propiedades = PropertiesService.getScriptProperties();
  var id = propiedades.getProperty('SPREADSHEET_ID') || ID_SPREADSHEET;
  var nombrePestana = propiedades.getProperty('SHEET_NAME');
  var archivo = SpreadsheetApp.openById(id);
  var hoja = nombrePestana ? archivo.getSheetByName(nombrePestana) : archivo.getSheets()[0];
  if (!hoja) throw new Error('No se encontró la pestaña configurada en Google Sheets.');
  return hoja;
}

// Localiza las columnas de gestión por nombre y usa posiciones previstas como respaldo.
function columnasDeGestion(hoja) {
  var encabezados = hoja.getRange(1, 1, 1, hoja.getLastColumn()).getDisplayValues()[0];
  var normalizados = encabezados.map(function(valor) {
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toUpperCase().replace(/\s+/g, ' ').trim();
  });
  var codigo = normalizados.findIndex(function(valor) { return valor.indexOf('CODIGO') !== -1; });
  var estado = normalizados.findIndex(function(valor) {
    return valor.indexOf('ESTADO') !== -1 && valor.indexOf('VALIDACION') !== -1;
  });
  var notificado = normalizados.findIndex(function(valor) { return valor.indexOf('NOTIFICADO') !== -1; });
  return {
    codigo: codigo >= 0 ? codigo + 1 : 9,
    estado: estado >= 0 ? estado + 1 : 11,
    notificado: notificado >= 0 ? notificado + 1 : 12
  };
}

// Busca exactamente una fila por código y devuelve también las columnas identificadas.
function buscarFilaPorCodigo(hoja, codigo) {
  var columnas = columnasDeGestion(hoja);
  var ultimaFila = hoja.getLastRow();
  if (ultimaFila < 2) throw new Error('No se encontró el código solicitado.');
  var codigos = hoja.getRange(2, columnas.codigo, ultimaFila - 1, 1).getDisplayValues();
  var coincidencias = [];
  for (var i = 0; i < codigos.length; i++) {
    if (String(codigos[i][0] || '').trim() === codigo) coincidencias.push(i + 2);
  }
  if (!coincidencias.length) throw new Error('No se encontró el código solicitado.');
  if (coincidencias.length !== 1) throw new Error('El código no es único en Google Sheets.');
  return { fila: coincidencias[0], columnas: columnas };
}

// Determina si el registro ya está aprobado o descartado.
function estadoEsFinal(estado) {
  var normalizado = String(estado || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  return normalizado === 'APROBADO' || normalizado === 'DESCARTADO';
}

// Reconoce las marcas afirmativas que indican que ya se envió la notificación.
function estadoEstaNotificado(valor) {
  var normalizado = String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  return ['SI', 'S', 'YES', 'TRUE', 'NOTIFICADO'].indexOf(normalizado) !== -1;
}

// Consulta el estado y la marca de notificación sin iniciar un nuevo envío.
function consultarNotificacion(codigo) {
  var hoja = obtenerHojaConfigurada();
  var encontrado = buscarFilaPorCodigo(hoja, codigo);
  var estado = hoja.getRange(encontrado.fila, encontrado.columnas.estado).getDisplayValue();
  var estadoNotificado = hoja.getRange(encontrado.fila, encontrado.columnas.notificado).getDisplayValue();
  var notificado = estadoEstaNotificado(estadoNotificado);
  return {
    ok: true,
    codigo: codigo,
    estado: estado,
    estado_guardado: estadoEsFinal(estado),
    estado_final: estadoEsFinal(estado),
    notificado: notificado,
    notificacion_enviada: false,
    ya_estaba_notificado: notificado,
    procesando: /^ENVIANDO/i.test(String(estadoNotificado || '').trim()),
    estado_notificado: estadoNotificado,
    mensaje: notificado ? 'La notificación ya está registrada.' : 'La notificación continúa pendiente.'
  };
}

// Serializa con un bloqueo el procesamiento del correo/PDF para evitar duplicados.
function procesarNotificacionPorCodigo(codigo) {
  var bloqueo = LockService.getScriptLock();
  if (!bloqueo.tryLock(30000)) {
    return {
      ok: false, codigo: codigo, estado_guardado: null, notificado: false, notificacion_enviada: false,
      estado_final: true, procesando: true,
      mensaje: 'Otro procesamiento está en curso; no se inició un segundo envío.'
    };
  }
  try {
    var hoja = obtenerHojaConfigurada();
    var encontrado = buscarFilaPorCodigo(hoja, codigo);
    var estado = hoja.getRange(encontrado.fila, encontrado.columnas.estado).getDisplayValue();
    var notificado = hoja.getRange(encontrado.fila, encontrado.columnas.notificado).getDisplayValue();
    if (!estadoEsFinal(estado)) {
      return {
        ok: false, codigo: codigo, estado: estado, estado_guardado: false, estado_final: false,
        notificado: estadoEstaNotificado(notificado), notificacion_enviada: false,
        mensaje: 'El estado guardado no es APROBADO ni DESCARTADO.'
      };
    }
    if (estadoEstaNotificado(notificado)) {
      return {
        ok: true, codigo: codigo, estado: estado, estado_guardado: true, estado_final: true,
        notificado: true, notificacion_enviada: false, ya_estaba_notificado: true,
        estado_notificado: notificado, mensaje: 'La notificación ya está registrada; no se volvió a enviar.'
      };
    }

    // Bajo el bloqueo compartido, cualquier marca ENVIANDO anterior quedó huérfana
    // (una ejecución activa aún conservaría el mismo bloqueo). Se permite reintentar.
    hoja.getRange(encontrado.fila, encontrado.columnas.notificado).setValue('ENVIANDO...');
    SpreadsheetApp.flush();
    var resultado = procesarUnaSolaFila(hoja, encontrado.fila, estado);
    return {
      ok: resultado.enviado,
      codigo: codigo,
      estado: estado,
      estado_guardado: true,
      estado_final: true,
      notificado: resultado.enviado,
      notificacion_enviada: resultado.enviado,
      ya_estaba_notificado: false,
      procesando: false,
      estado_notificado: resultado.enviado ? 'SÍ' : 'ERROR',
      mensaje: resultado.enviado ? 'Notificación enviada y registrada.' : 'No se pudo enviar la notificación.',
      error: resultado.error || ''
    };
  } finally {
    bloqueo.releaseLock();
  }
}

// Endpoint servidor-servidor: autentica el token y ejecuta consultar o procesar.
function doPost(e) {
  try {
    var datos = e && e.postData && e.postData.contents ? JSON.parse(e.postData.contents) : {};
    var tokenConfigurado = PropertiesService.getScriptProperties().getProperty('PYTHON_WEBHOOK_TOKEN');
    if (!tokenConfigurado || !compararSecreto(datos.token, tokenConfigurado)) {
      return jsonRespuesta({ ok: false, error: 'No autorizado.' });
    }
    var codigo = String(datos.codigo || '').trim();
    if (!codigo) return jsonRespuesta({ ok: false, error: 'El código es obligatorio.' });
    var accion = String(datos.accion || 'procesar').toLowerCase();
    var resultado = accion === 'consultar'
      ? consultarNotificacion(codigo)
      : accion === 'procesar'
        ? procesarNotificacionPorCodigo(codigo)
        : { ok: false, error: 'La acción solicitada no está permitida.' };
    return jsonRespuesta(resultado);
  } catch (error) {
    console.error('Error en doPost: ' + error.message);
    return jsonRespuesta({ ok: false, estado_guardado: null, error: error.message || 'Error interno de Apps Script.' });
  }
}

// Guarda una solicitud recibida desde el formulario web, asigna código y avisa al solicitante.
function guardarGasto(datos) {
  try {
    var hoja = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var montoFloat = parseFloat(datos.monto) || 0;
    
    var correoLimpio = datos.correo ? datos.correo.toString().trim().toLowerCase() : "";
    var nombresMayus = datos.nombres ? datos.nombres.toString().trim().toUpperCase() : "";
    var areaMayus = datos.area ? datos.area.toString().trim().toUpperCase() : "";
    var motivoMayus = datos.motivo ? datos.motivo.toString().trim().toUpperCase() : "";
    
    var estadoLegal = (montoFloat > 45.20) ? "EXCEDE EL 4% RMV" : "DENTRO DEL LÍMITE";
    var firmaBase64 = datos.firma ? datos.firma.toString() : IMAGEN_VACIA_BASE64;
    
    var fechaExacta = "'" + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss"); 

    hoja.appendRow([
      fechaExacta, correoLimpio, nombresMayus, 
      datos.dni, areaMayus, motivoMayus, montoFloat, firmaBase64
    ]);
    
    var nuevaFila = hoja.getLastRow();
    var nuevoCorrelativo = generarNuevoCorrelativo(hoja);
    
    hoja.getRange(nuevaFila, 9, 1, 4).setValues([[nuevoCorrelativo, estadoLegal, "PENDIENTE", "NO"]]);
    
    aplicarFormatoFila(hoja, nuevaFila);

    if (correoLimpio !== "") {
      var firmaHTML = obtenerFirmaInstitucional();
      MailApp.sendEmail({
        to: correoLimpio,
        subject: "⏳ [EN PROCESO] Solicitud de Movilidad " + nuevoCorrelativo,
        htmlBody: "<p>Estimado/a <b>" + nombresMayus + "</b>,</p><p>Hemos recibido tu registro web (<b>" + nuevoCorrelativo + "</b>) por <b>S/. " + montoFloat.toFixed(2) + "</b>.</p><p>Actualmente se encuentra <b>EN PROCESO</b> de validación.</p>" + firmaHTML
      });
    }
    return "¡Registro exitoso! Código asignado: <b>" + nuevoCorrelativo + "</b>.";
  } catch(e) {
    return "Error al guardar, pero el servidor respondió: " + e.message;
  }
}

// ============================================================================
// PUERTA 2: ENTRADA DESDE EL GOOGLE FORMS (CON AUTO-ORDENADOR)
// ============================================================================
// Normaliza la respuesta de Forms, asigna datos de gestión y envía el aviso de recepción.
function alEnviarFormulario(e) {
  try {
    var hoja = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var fila = hoja.getLastRow();
    
    if (e && e.range) {
      fila = e.range.getRow();
    }
    
    var ultimaFilaReal = hoja.getLastRow();
    
    // MAGIA: Si Forms insertó la fila arriba empujando datos, la movemos al fondo.
    if (fila > 1 && fila < ultimaFilaReal) {
      var numColumnas = hoja.getLastColumn();
      var datosExtraidos = hoja.getRange(fila, 1, 1, numColumnas).getValues()[0];
      hoja.deleteRow(fila); // Borramos la fila desordenada
      hoja.appendRow(datosExtraidos); // La enviamos al verdadero final
      SpreadsheetApp.flush(); 
      fila = hoja.getLastRow(); // Ahora trabajaremos con la verdadera última fila
    }
    
    var datosFila = hoja.getRange(fila, 1, 1, 8).getValues()[0];
    var correo = datosFila[1] ? datosFila[1].toString().trim().toLowerCase() : "";
    var nombresMayus = datosFila[2] ? datosFila[2].toString().trim().toUpperCase() : "";
    var areaMayus = datosFila[4] ? datosFila[4].toString().trim().toUpperCase() : "";
    var motivoMayus = datosFila[5] ? datosFila[5].toString().trim().toUpperCase() : "";
    var monto = parseFloat(datosFila[6]) || 0;
    
    var fechaExacta = "'" + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss");
    hoja.getRange(fila, 1).setValue(fechaExacta);
    hoja.getRange(fila, 3).setValue(nombresMayus);
    hoja.getRange(fila, 5).setValue(areaMayus);
    hoja.getRange(fila, 6).setValue(motivoMayus);

    var nuevoCorrelativo = generarNuevoCorrelativo(hoja);
    var estadoLegal = (monto > 45.20) ? "EXCEDE EL 4% RMV" : "DENTRO DEL LÍMITE";

    hoja.getRange(fila, 9, 1, 4).setValues([[nuevoCorrelativo, estadoLegal, "PENDIENTE", "NO"]]);
    aplicarFormatoFila(hoja, fila);

    if (correo !== "") {
      var firmaHTML = obtenerFirmaInstitucional();
      MailApp.sendEmail({
        to: correo,
        subject: "⏳ [EN PROCESO] Solicitud de Movilidad " + nuevoCorrelativo,
        htmlBody: "<p>Estimado/a <b>" + nombresMayus + "</b>,</p><p>Hemos recibido tu registro vía Forms (<b>" + nuevoCorrelativo + "</b>) por <b>S/. " + monto.toFixed(2) + "</b>.</p><p>Actualmente se encuentra <b>EN PROCESO</b> de validación.</p>" + firmaHTML
      });
    }
  } catch(error) {
    console.error("Error en alEnviarFormulario: " + error.message);
  }
}

// ============================================================================
// GESTIÓN DE APROBACIÓN
// ============================================================================
// Activador de edición: detecta cambios de estado y procesa el aviso cuando es final.
function alCambiarEstado(e) {
  if (!e) return;
  var hoja = e.range.getSheet();
  var fila = e.range.getRow();
  var columnas = columnasDeGestion(hoja);

  if (e.range.getColumn() === columnas.estado && fila > 1) {
    var estadoValidacion = String(e.value || '').toUpperCase().trim();
    if (estadoValidacion === 'PENDIENTE' || !estadoValidacion) {
      hoja.getRange(fila, columnas.notificado).setValue('NO');
      return;
    }
    if (estadoEsFinal(estadoValidacion)) {
      var codigo = String(hoja.getRange(fila, columnas.codigo).getDisplayValue() || '').trim();
      try {
        procesarNotificacionPorCodigo(codigo);
      } catch (error) {
        console.error('Error en alCambiarEstado: ' + error.message);
      }
    }
  }
}

// Genera el comprobante PDF si se aprueba o envía el correo de rechazo si se descarta.
function procesarUnaSolaFila(hoja, fila, estadoValidacion) {
  var columnas = columnasDeGestion(hoja);
  try {
    if (!estadoEsFinal(estadoValidacion)) throw new Error('El estado de validación no es final.');
    var estadoNormalizado = String(estadoValidacion).normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
    var datosFila = hoja.getRange(fila, 1, 1, 12).getValues()[0];
    
    var fechaCruda = datosFila[0];
    var fechaFormateada = "";
    if (fechaCruda instanceof Date) {
      fechaFormateada = Utilities.formatDate(fechaCruda, Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm:ss");
    } else {
      fechaFormateada = String(fechaCruda).replace(/^'/, ''); 
    }

    var correoEnvio = String(datosFila[1]).toLowerCase(); 
    var correoMayus = String(datosFila[1]).toUpperCase(); 
    var nombresMayus = String(datosFila[2]).toUpperCase();         
    var dniStr = String(datosFila[3]);             
    var areaMayus = String(datosFila[4]).toUpperCase();            
    var motivoMayus = String(datosFila[5]).toUpperCase();          
    var montoFloat = parseFloat(datosFila[6]) || 0; 
    var firmaUrlForms = datosFila[7] ? datosFila[7].toString() : ""; 
    var correlativoMayus = String(datosFila[8]).toUpperCase();     
    var estadoLegalMayus = String(datosFila[9]).toUpperCase();     
    var estadoValMayus = estadoNormalizado;

    var firmaHTML = obtenerFirmaInstitucional();

    if (estadoNormalizado === 'APROBADO') {
      
      var ID_PLANTILLA = '1FHDuL9thnWQh5lVEoW6142u-cl1TojysZEmtmFrjLkA';
      var plantilla = DriveApp.getFileById(ID_PLANTILLA);
      var archivoCopia = plantilla.makeCopy("Movilidad_" + correlativoMayus);
      var copiaId = archivoCopia.getId();
      
      var doc = DocumentApp.openById(copiaId);
      var body = doc.getBody();

      body.replaceText("\\{\\{CORRELATIVO\\}\\}", correlativoMayus);
      body.replaceText("\\{\\{NOMBRES\\}\\}", nombresMayus);
      body.replaceText("\\{\\{CORREO\\}\\}", correoMayus);
      body.replaceText("\\{\\{DNI\\}\\}", dniStr);
      body.replaceText("\\{\\{ÁREA\\}\\}", areaMayus);
      body.replaceText("\\{\\{FECHA\\}\\}", fechaFormateada);
      body.replaceText("\\{\\{MOTIVO\\}\\}", motivoMayus);
      body.replaceText("\\{\\{CANTIDAD\\}\\}", "S/. " + montoFloat.toFixed(2));
      body.replaceText("\\{\\{CONTROL\\}\\}", estadoLegalMayus);
      body.replaceText("\\{\\{ESTADO\\}\\}", estadoValMayus);
      body.replaceText("\\{\\{MONTO\\}\\}", "S/. " + montoFloat.toFixed(2));

      var blobJefe = DriveApp.getFileById(ID_FIRMA_JEFE).getBlob();
      var blobAdmin = DriveApp.getFileById(ID_FIRMA_ADMIN).getBlob();
      var blobTrabajador = obtenerBlobDeFirma(firmaUrlForms);
      
      insertarImagenEnDoc(body, "\\{\\{FIRMA_JEFE\\}\\}", blobJefe);
      insertarImagenEnDoc(body, "\\{\\{FIRMA_ADMIN\\}\\}", blobAdmin);
      insertarImagenEnDoc(body, "\\{\\{FIRMA_TRABAJADOR\\}\\}", blobTrabajador);

      doc.saveAndClose();

      var ID_CARPETA_DESTINO = '1_IUnNnMG04eE2vZv2fZUIsdDvtZdAnUA';
      var carpeta = DriveApp.getFolderById(ID_CARPETA_DESTINO);

      var pdfBlob = archivoCopia.getAs(MimeType.PDF).setName("Movilidad_" + correlativoMayus + ".pdf");
      var archivoPDFGuardado = carpeta.createFile(pdfBlob); 

      MailApp.sendEmail({
        to: correoEnvio,
        subject: "✅ [APROBADO] Comprobante " + correlativoMayus,
        htmlBody: "<p>Estimado/a <b>" + nombresMayus + "</b>,</p><p>Su solicitud <b>" + correlativoMayus + "</b> ha sido <b style='color: #0F9D58;'>APROBADA</b>.</p><p>Adjuntamos la boleta electrónica correspondiente.</p>" + firmaHTML,
        attachments: [archivoPDFGuardado.getAs(MimeType.PDF)]
      });

      archivoCopia.setTrashed(true);

    } else if (estadoNormalizado === 'DESCARTADO') {
      MailApp.sendEmail({
        to: correoEnvio,
        subject: "❌ [DESCARTADO] Solicitud " + correlativoMayus,
        htmlBody: "<p>Estimado/a <b>" + nombresMayus + "</b>,</p><p>Su solicitud <b>" + correlativoMayus + "</b> ha sido <b style='color: #d93025;'>DESCARTADA</b>.</p>" + firmaHTML
      });
    }
    
    hoja.getRange(fila, columnas.notificado).setValue('SÍ');
    return { enviado: true, error: '' };
  } catch(error) {
    console.error("Error en procesarUnaSolaFila: " + error.message);
    hoja.getRange(fila, columnas.notificado).setValue('ERROR');
    return { enviado: false, error: error.message || 'Error de notificación.' };
  }
}