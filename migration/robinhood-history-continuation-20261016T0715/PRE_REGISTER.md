# Protocolo previo: segundo intervalo anterior y observación única

Este ensayo continúa PR13 sin cambiar sus fuentes ni resultados. Antes de la
primera consulta se publicarán esta política, código y hashes. Objetivo:
ampliar la cobertura observable del mercado wsNET/USDG de Morpho, Robinhood 4663.
No mide ingresos, captura, inclusión, rutas ni nuevos costes Nitro/DA.

Fuente: `migration/robinhood-history-backfill-20261016/evidence/pilot/registry.json`
del commit `66f0abbf6d44c6e98a0070b2109ee375ae42de3b`; raíz SHA-256
`3659ce75ace86563b3a3c6ddbed5382b98566db332c5fc57116c7885308a70f4`.
Su fichero y la ventana fija están vinculados por hashes en `policy.json`.

Se añaden exactamente **400,000 bloques anteriores, 88,646,281–89,046,280**,
en 40 tramos de 10,000. La regla depende solo del comienzo del registro previo,
sin usar salud ni liquidaciones conocidas. Se conservan todas las cuentas de
Borrow onBehalf y se revalidan checkpoints y frontera. Después de unir en una
copia, se actualiza la cola hasta la primera cabecera recibida en esa fase menos
64 bloques. No se saltan huecos; el buffer no se presenta como finalidad.

Se conservan los límites conjuntos de 512 eventos, 128 alturas con eventos y
64 cuentas, y un máximo de 40 tramos por fase. Ante exceso o fallo se detiene,
sin recortar cuentas ni ampliar el presupuesto. Los prefijos se guardan con su
fase, sin promocionarlos a una cohorte que cubra el objetivo completo.

El nuevo auditor distingue estado anterior, unión persistida y actualización
reciente. Se prueba la interrupción en cada petición de una ejecución sintética,
además de errores HTTP/JSON, presupuesto, cadena incorrecta y reorgs. Esas pruebas
no sustituyen la medición real. El auditor anterior permanece intacto; el nuevo
tiene una regresión sobre todas las métricas del piloto real de PR13.

Una vez terminada la ventana completa se congela la cohorte antes de consultar
posiciones, se autentican los runtimes/parámetros como en PR13, y se observan
**tres cabeceras posteriores, distintas y crecientes**. Se reutiliza sin cambios
el initcode de lectura de PR13: un `eth_call` con `to` omitido, sin overrides,
gas máximo 2,000,000 y llamadas externas STATICCALL. No se despliega ni se envía
una transacción. No se repite batch: la comparación de PR13 ya existe y esta
medición busca cobertura adicional, no una nueva prueba de velocidad relativa.

Cada lectura fija hash con `requireCanonical` y revalida después la cabecera.
Se conservan los tiempos hasta obtener entradas y se añaden:

- Desde recibir la cabecera hasta terminar la comprobación canónica y registrar
  el resultado de la lectura.
- Desde iniciar la petición de cabecera hasta ese mismo punto.
- Desde iniciar la lectura hasta ese mismo punto.

Estas métricas incluyen pasos que el tiempo de entradas excluye; no incluyen
simulación de ruta, bundler, envío ni inclusión. El límite de 1,000 ms sigue
siendo una hipótesis de ingeniería, no una ventana de mercado comprobada.

La cobertura usa borrowShares del mismo bloque; se comparará la cohorte fuente
con la ampliada sobre ese mismo estado. Cuentas sin deuda se conservan. Se usa
el umbral de salud heredado, 100 bps. Una señal no acredita oportunidad rentable.
Beneficio realizado y tasa de captura siguen como `null`, no como cero medido.

Presupuesto global por ejecución: 512 métodos RPC y 900 s comprobados antes de
cada POST, con hasta 20 s adicionales de la petición ya iniciada; 2 MiB por
respuesta y 32 MiB total. Un endpoint documentado, sin HTTP paralelo, reintentos,+cambios de proveedor tras rechazo, firmas reales, transacciones o gastos.
Un fallo conserva respuestas y estado parcial. Un auditor que rechaza evidencia
no permite declarar éxito ni descartar silenciosamente datos.

No hay prueba criptográfica de completitud de logs/estado, segunda fuente,
historia desde el origen o garantía sobre bloques posteriores al checkpoint.
Los hashes vinculan el paquete publicado; no certifican por sí solos al proveedor
o el reloj local. Las referencias de interfaz y compilación están en el protocolo
inmutable de PR13; no se cambia ninguna interfaz de red o contrato en este ensayo.
