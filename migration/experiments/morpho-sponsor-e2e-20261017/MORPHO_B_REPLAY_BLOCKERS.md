# Caso B — BLOCKED_PRESTATE

Transacción de terceros: `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`, bloque 26190955, índice 1. Única transacción precedente: `0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`.

Disponible y preservado en el directorio anterior: bloque completo, 602 sobres de transacción y su raíz, recibo B cruzado con el evento Morpho, observaciones de flujo Fluid/ETH/WETH, cálculos enteros y hashes. Las 168 regresiones Python, incluida la verificación de orden, volvieron a pasar. No se repitieron llamadas archivísticas denegadas ni se generó un estado sustituto.

**Primer input ausente:** testigo autenticado de cuentas, código y storage del estado padre, anclado a su stateRoot. No existe un archivo válido de ese testigo en el expediente. A continuación faltan las transiciones de sistema aplicables y la ejecución de tx0 que llevan al estado anterior a tx1. El estado al cierre del bloque anterior no es automáticamente el prestate de B.

| Dato ausente | Consecuencia exacta |
|---|---|
| Posición Morpho, totales de mercado, storage del IRM y timestamp coherentes | No calcular de forma autenticada intereses, debt shares ni cantidad liquidable antes del evento |
| Oracle/configuración/proxies al índice correcto | No acreditar que el precio que habilita liquidar estaba disponible entonces |
| Estado Fluid: reservas reales/imaginarias, balances, límites y parámetros temporales | No reproducir la salida ejecutable ni asegurar capacidad de conversión |
| Efectos completos de tx0 y transiciones de sistema | No certificar que ninguna dependencia relevante cambió dentro del bloque |
| Ejecución original con paridad de recibo/logs/gas | No certificar el contrafactual NQC ni su gas |
| Financiación y señal anteriores al cutoff | No acreditar capital cero comercial ni captura |

Contabilidad fija ya conocida del tercero: salida Fluid 26.409680973611 ETH; deuda 26.039738525656992415 WETH; tip completo 0.368092735714237547 ETH; gas 745,509 × 266,148,625 wei/gas. Residual aritmético: **0.001651296044494913 ETH**, antes de partidas externas desconocidas. Los 0.006392502690919791 WETH iniciales se excluyen del ingreso. No se asigna el tip al builder. A 3 gwei y manteniendo las demás partidas constantes: **−0.000386814760229962 ETH**. Estos son límites/cálculos de terceros, no beneficios reproducidos ni realizados de NQC.

El experimento local nuevo usa V2 y tokens de laboratorio; no se denomina replay Fluid ni caso B. Los hashes de transacciones no son testigos de storage. La línea histórica queda pausada por falta de inputs; los 403/405/null/poda y límites de infraestructura previos permanecen como limitaciones, no obstáculos que se intentaron eludir.

Corrección temporal adoptada: la ventana anterior de 95 segundos fue elegida 0.585742 s después de terminar; tampoco había mismo bloque para mercado/posición/oracle. No acredita prerregistro prospectivo. No se desplegó monitor ni se hizo una nueva observación de mercado en este estudio local.
