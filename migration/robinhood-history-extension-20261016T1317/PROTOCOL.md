# Prerregistro: extensión histórica 87846281–88246280

Este protocolo se publica con código, política y hashes antes de cualquier RPC. No modifica PR19 ni vuelve a ejecutar su ventana. El incremento es una captura de cobertura, no otra comparación de transportes ni una prueba de ingresos.

Base `ca184cdd14d8d5a8a4d447a9723a0e792dc00132`. Fuente real PR19 `migration/robinhood-paced-history-20261016T1222/evidence/pilot/registry.json`, raíz `e9dfe58703e31d07eb8a61be6ee46f62d5b13679c7e78feb286ce47e4d88ceca`, SHA archivo `8cbbeac9381cfdb0a011bd5a74a06c80b07cc755e999b50b42e920dbe0a05dba`. Prefijo 88246281–90080877, 97 Borrow, 46 cuentas. No usar trazas sintéticas como fuente.

## Cambios y ejecución única

Se reutiliza SIN MODIFICAR el motor PR19. `continue_history.py` dirige únicamente su carga de política/lock al directorio nuevo; restaura esa referencia al terminar. `audit_extension.py` suministra la política nueva explícitamente al replay inmutable. No se invoca el main con su política/ventana antigua. Los únicos cambios de política son identidad, ventana y fuente. Dependencias y APIs heredadas, sin APIs nuevas.

1. Verificar dependencias exactas PR15, todas las fuentes fijadas, fuente real y ausencia de captura/proceso duplicado.
2. Abrir una sesión persistente y un único contador/plazo/gate. Validar chainId, checkpoint de fuente y frontera anterior canónica.
3. Indexar EXACTAMENTE 400000 bloques 87846281–88246280, en 40 segmentos de 10000, validando cabeceras/eventos y anchor. Guardar `older-registry.json` por prefijo.
4. Unir con la fuente sin huecos, revalidar checkpoint previo, conservar `merged-before-catchup.json` y `registry.json`. Se reconstruyen enlaces SHA de segmentos, no sus payloads.
5. Obtener latest/anchor vigente con buffer64, continuar SOLO cola desde90080878, dentro del MISMO presupuesto. Canon y auth antes de congelar. Si el target no termina, no congelar.
6. Congelar todas las cuentas (también deuda cero), máximo64, sin clasificación por salud ni liquidaciones conocidas. Si se supera el límite, detener sin recortar ni ampliar retrospectivamente; preservar el registro y publicar protocolo posterior si se necesita capacidad mayor.
7. Tres lecturas secuenciales: cabecera latest, lens único por hash, verificación canónica, misma sesión sin rotación. Conciliar totalBorrowShares por hash. Retener lentas/cabeceras repetidas; rechazar regresiones/reorgs. No consultas adicionales al finalizar.

## Límites globales y conservación

Máximo512 métodos RPC/900s desde inicializar el lector, preparación y esperas incluidas. Gate global350ms entre inicios locales, sin crédito acumulable/reset entre historia, unión, cola, auth u observaciones. No garantiza llegada al servidor, cuota ni SLA. Un máximo40 segmentos por fase NO reinicia el contador/plazo global. Respuesta2MiB, acumulado32MiB, timeout20s y restante global. Límites originales de logs/eventos/cuentas sin cambios.

Endpoint único `https://docs-demo.robinhood-mainnet.quiknode.pro/`; TLS verificado y configuración proxy/no_proxy/CA existente. Sin reintentos, redirecciones, HTTP paralelo, sesiones de rescate, proveedor alternativo o modificación de red para evadir rechazo. Cualquier error/429/denegación detiene TODO; conservar cuerpos, prefijos y rechazo. Nunca reemplazar la captura ni convertir una parada en éxito. No trading, firmas, transacciones, gastos, suscripciones o despliegues.

## Métricas y criterios

Primaria desde ANTES de admisión de cabecera hasta estado verificado, incluyendo espera; secundaria desde despacho HTTP claramente separada. Tres solicitudes implican >=1050ms de cadencia sostenida mínima bajo gate350ms; no ocultar espera para forzar PASSsubsegundo. Esta muestra breve no mide adquisición fría, ciclo de trading, gas/AA/Nitro/DA o financiación. Registrar cadencias observadas sin extrapolar SLA.

Reportar bloques/eventos/cuentas añadidas por historia y cola, cobertura/faltante y candidatos SOLO si ocurrieron observaciones. Comparar contribución de cohorte anterior/nuevas sobre los mismos hashes, no entre momentos. Ausencia de observación no significa cero candidatos. Deuda no equivale a dólares ni ingresos. Objetivo comercial aún pendiente.

Offline antes de RPC: seis pruebas de política/adaptador, diez regresiones PR19 con43fronteras sintéticas, siete verificaciones de su muestra anterior y nueve aislamiento. No reimplementar gate/auditor sin defecto demostrado. Replay real posterior debe reconstruir exactamente archivos parciales o completos; mantener protocolos/blobs/workflows anteriores intactos. Prerregistro no contiene todavía datos de esta captura.
