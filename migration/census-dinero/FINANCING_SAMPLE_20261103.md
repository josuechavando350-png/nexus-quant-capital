# Shadow: muestra y financiación Titan / flash

Directiva reafirmada por el usuario: Titan financia el gas; préstamos flash
aportan el principal. Aportación propia cero, sin prefondos ni alternativa de gas
propio. La política ya estaba fijada en
[Omega](https://github.com/josuechavando350-png/nexus-quant-capital/blob/96583258fefe9c1a3f5595dbc3f35b58814162bd/omega/TITAN_GAS_POLICY.md).

## Trabajo en marcha

- Shadow v12, run **41571735530**, productor
  `51e79b7a4b8bfa19d82f9940072eb635b7cb8e3c`: ventana de 330 minutos,
  19 mercados Base/Morpho. No reiniciar una observación activa.
- Su primer parcial, hasta bloque **53443691**, contiene 275 bloques procesados,
  cinco NO-GO por deuda mala y cero liquidaciones observadas. Es un parcial,
  no el desenlace de la corrida. El acumulado anterior tenía 0/20 casos admitidos.
- Census v12, run **41572304605**, productor
  `259a796ee96433c4fea1c026b4040440aa644234`: recuperación de ocho cadenas.
  Sei y Corn fallaron; Soneium terminó su job, pero su cobertura debe revisarse.
  Las otras cinco siguen en curso en este checkpoint.

## Qué añade este cambio

Cada decisión nueva conserva `financiacion` con chain ID, número y hash observado
del bloque, parámetros y estado del mercado, posición, precio del oráculo,
decimales, cálculo raw y principal modelado del préstamo. Los enteros raw se
guardan como cadenas decimales para evitar pérdida de precisión en lectores JS.
Una prueba reconstruye exactamente la cotización con esa captura.
La captura se toma antes del crítico: si este corrige una discrepancia del libro,
se conserva la entrada que se cotizó y la lectura correctora queda por separado.

Las lecturas originales usan número de bloque: el hash observado **no** certifica
que todas las respuestas provengan de un estado anclado por hash. Antes de una
simulación propia se debe revalidar canonicalidad y releer el estado necesario.
El interés puede estar acumulado por el modelo y queda identificado como tal.
El estado total de Morpho no prueba liquidez flash disponible del prestamista.

No añade consultas a la ruta crítica ni cambia GO/NO-GO o la admisión de muestra.
Las decisiones de la corrida activa usan el productor anterior; este formato
entrará en la siguiente observación. No se reescriben registros históricos.

El reporte cuenta capturas y datos pendientes. `neto_modelo_usd` conserva su
significado de prior de retención de otros liquidadores. No es una simulación
de nuestra ruta. Neto propio, comisión flash, cobertura Titan y beneficio
realizado permanecen desconocidos. Los precios USD de préstamos USDC que usa
Shadow son un supuesto de USD 1 por USDC, no un precio de salida de swap.

## Prueba económica pendiente

1. Cotizar una ruta propia al mismo estado: prestamista, liquidez, prima y swaps.
2. Simular atómicamente liquidación, conversión y devolución del préstamo.
3. Verificar cobertura de Titan para la cadena y candidata concretas, gas y
   reembolso, tarifas L1/L2 y compensación del builder sin doble conteo.
4. Separar excedente simulado, probabilidad de inclusión y beneficio realizado.

La [documentación oficial de Titan](https://docs.titanbuilder.xyz/api/eth_sendbundle)
exige que el bundle permita recuperar el patrocinio. No demuestra cobertura
específica en Base ni aceptación de una candidata NQC. El testigo histórico H24
de Morpho es Ethereum, chain ID 1: su prima observada cero no se extrapola a estas
candidatas, ni su residual se convierte en beneficio NQC.

## Continuación acotada

Mantener el criterio de muestra: eventos únicos por tx/logIndex, bono mínimo
USD 1, ventana medida desde el mismo origen, sin rellenar tiempos ni convertir
20 ms de envío supuesto en medición. Los 20 casos solo abren revisión.

Actualizar la revisión existente `6ae95504c1c48191a378e3e66159bffe` a cuatro
controles separados por seis horas, comenzando en `2026-11-03T09:29:08Z`.
En los tres primeros, si la muestra sigue incompleta y no hay Shadow activo,
continuar como máximo una ventana de 330 minutos por control con la configuración
de `runs/shadow-v12.json`. El cuarto control solo informa. Detener la continuación
si se alcanza la muestra o aparece un fallo que impida medirla con integridad.
No repetir Census fallidos a ciegas. No nuevas automatizaciones, servicios,
firmas, transacciones, fondos ni modificaciones de workflows.

## Verificación

- 336 pruebas Python offline: OK, incluidas reproducción de cotización y
  separación entre prior, captura y P&L; no certifican economía en red.
- `check_isolation.py`: `ISOLATED_SOURCE_IDENTITY_PASS`; 531 originales,
  106 workflows históricos deshabilitados. `original_objects_checked=false`:
  no se afirma recertificación de objetos originales en este checkout superficial.
- Sin cambios en `run.json` ni workflows; este commit no reinicia los jobs activos.
