# Prerregistro: historia contigua 87446281–87846280

Publicar este protocolo, código, política y hashes antes de RPC. Base PR20 `976aecb3e25118b1531772d7778668ee34b97d61`. Captura única nueva, no repetición del runner PR20 ni benchmark de transportes. Todavía no hay medición de esta ventana al registrar.

Fuente real `migration/robinhood-history-extension-20261016T1317/evidence/pilot/registry.json`; raíz `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`; SHA archivo `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`. Prefijo 87846281–90109721,125 Borrow,52 cuentas. No usar synthetic como fuente.

## Reutilización y orden fijo

Motor PR19 inmutable; adaptadores PR20 copiados sin cambios de comportamiento. El nuevo directorio carga únicamente política/lock nuevos; auditor recibe explícitamente esta política. No se ejecutan ventanas antiguas. Solo cambian identidad, fuente y límites de la ventana (no límites de recursos).

1. Verificar dependencias exactas PR15, fuentes, fuente real y ausencia de proceso/captura duplicados. Crear una sola sesión, gate y presupuesto global.
2. Validar chainId, checkpoint de fuente y frontera canónica. Indexar 400000 bloques 87446281–87846280,40 segmentos de10000, con checks de eventos/cabeceras y anchor. Conservar prefijos en older-registry.json.
3. Unir sin huecos con fuente, revalidar checkpoint previo, guardar merged-before-catchup.json y registry.json. Reconstruir enlaces SHA, conservar payloads de eventos/checkpoints/respuestas. No afirmar identidad byte a byte de enlaces reconstruidos.
4. Obtener latest/anchor vigente con buffer64; actualizar SOLO cola desde90109722 dentro del MISMO presupuesto. Autenticar target antes de congelar. No congelar si target incompleto.
5. Conservar todas las cuentas, incluidas deuda cero, selección independiente de salud/liquidaciones conocidas. Límite64 sin recorte ni ampliación retrospectiva; si impide avanzar detener y preservar el estado válido y las respuestas, preparar otro protocolo después.
6. Tres observaciones secuenciales, misma sesión sin rotación: cabecera latest, lectura única lens por hash, verificación canónica. Conciliar totalBorrowShares en cada hash. Retener lentas y cabeceras repetidas; rechazar regresiones/reorgs. Ningún RPC posterior al término/error.

## Límites y parada

512 métodos RPC/900s TOTAL, preparación/esperas incluidas; gate350ms entre despachos locales, sin crédito acumulable ni reset entre fases/conexiones. Máximo40 segmentos por fase NO reinicia presupuesto. Límites previos de cuerpos2MiB/acumulado32MiB, timeout20s y restante global, logs/eventos/cuentas inalterados. Separación local no prueba llegada al servidor, cuota ni SLA.

Único endpoint `https://docs-demo.robinhood-mainnet.quiknode.pro/`. TLS verificado y configuración proxy/no_proxy/CA existente intacta. Sin reintentos, redirecciones, HTTP paralelo, sesiones de rescate, proveedor alternativo ni cambios de red para saltar denegaciones. Error/429/denegación detiene TODO; conservar cuerpo y prefijos, nunca reemplazar captura. Sin firmas, trading, envíos, gastos, suscripciones o despliegues.

## Métricas y verificación

Latencia primaria desde ANTES de admisión de cabecera hasta estado verificado; secundaria desde despacho claramente separada. Incluir esperas y reportar cadencias: tres solicitudes bajo gate350ms implican >=1050ms de cadencia sostenida mínima, no forzar subsegundo ocultando tiempo. Tres lecturas son muestra de cobertura, no benchmark ni prueba de adquisición fría, ruta/inclusión/gas/AA/Nitro/DA/financiación.

Reportar bloques/Borrow/cuentas por historia/cola, cobertura/faltante y candidatos solo si hay observaciones. Atribuir cambios con cohortes evaluadas en mismos hashes, no diferencias entre momentos. Ausencia de observación no equivale a cero candidatos; deuda/simulación no son ingresos.

Offline antes de RPC: seis pruebas adaptadas de política/entrada,10 regresiones de motor (43fronteras sintéticas),siete del informe PR20,nueve aislamiento. Reutilizar sin reimplementar pruebas anteriores. Replay posterior debe reproducir exactamente journal, ledger, admisiones y cuatro archivos de estado. Protocolos previos, originales y workflows deshabilitados intactos. Rentabilidad sigue sin demostrar.
