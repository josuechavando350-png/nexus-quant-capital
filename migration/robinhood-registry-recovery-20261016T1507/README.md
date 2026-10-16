# Recuperación de dos fuentes y separación de capacidad

El límite acumulado de bloques con eventos pasa a una cota explícita de 256. Cada segmento/respuesta conserva su límite de 128; cuentas 64, eventos 512, gas de lectura, bytes, gate y presupuesto no cambian. El índice previo y los 400000 bloques separados se recuperan desde sus archivos conservados, sin repetir ese escaneo.

Este documento registra preparación, **no una captura ya ejecutada**. Código, reglas y fuentes se fijan antes de medir; el resultado posterior se publicará por separado en `CAPTURE.md` y `evidence/`. Un rechazo previo sigue siendo rechazo histórico.

Leer [PROTOCOL.md](PROTOCOL.md) y `policy.json`. `recovery.py` usa una sesión y un presupuesto para revalidar, unir, actualizar solo cola, autenticar y observar tres hashes. `audit_recovery.py` reconstruye estados y paradas offline. Los módulos anteriores permanecen intactos.

La recuperación offline de datos reales produce 145 eventos/54 cuentas como comprobación estructural. No determina deuda actual, candidatos, gas o beneficio. El usuario no dispone de capital principal; disponibilidad de préstamo flash, financiación efectiva del gas/fallos y margen repetible siguen pendientes de prueba.
