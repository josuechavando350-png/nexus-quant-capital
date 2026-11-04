# Cierre NQC Titan / flash — 3 noviembre 2026 (México)

Cuarto y último control. Tres continuaciones completadas; no se inicia ni programa otra ventana. Política: gas exclusivamente Titan, principal flash, aportación propia cero.

## Resultado

18 corridas, 50.79 horas de ventanas acumuladas (no observación ininterrumpida), 196 eventos únicos tx/logIndex. Muestra válida **0/20**; alcanzar 20 habría abierto revisión, no certificado rentabilidad.

Embudo excluyente: 51 eventos por vía no directa, 53 por bono inferior/no medido, 92 por falta de trozo posterior medido. No duplicados, conflictos ni líneas inválidas en el acumulado. Umbral USD 1; envío rápido supuesto 20 ms. Se conservan holguras negativas.

## Último productor

[Run 41722601722](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/41722601722), source `2306700a00158e148d9c210ef7ee3293def5d258`. Plan, observación y reporte terminaron correctamente. Ese éxito no resuelve las puertas de validación.

185 liquidaciones nuevas, 185 identidades únicas. 44 fuera del libro conocido antes del evento: 35 cbBTC/USDC, 8 JitoSOL/USDC y 1 SOL/USDC. Causa pendiente; la puerta de detección falla. No se atribuyen a falta de oportunidades.

Bloques 53476105–53486009: 9,890 medidos individualmente de 9,905 (99.8486%); 15 cubiertos por recuperación de eventos. El 100% del resumen está redondeado. Recuperar eventos no recupera tiempos. Cuatro cierres WebSocket con reconexión y errores HTTP transitorios; no se certifica cobertura íntegra de preconfirmaciones.

La clasificación de rivales por propinas no sustituye un trozo posterior medido. El evaluador pendiente usa su supuesto histórico de 150 ms; la muestra rápida usa 20 ms. Ninguno mide un envío real.

## Economía

Cinco capturas finales reproducidas exactamente con aritmética entera; 16 entre las tres continuaciones. Una GO modelada al inicio, con cruce incierto, expiró: principal modelado 67.518457 USDC, bono de oráculo 2.960097 USDC. No son salida de swap ni beneficio. Otras cuatro NO-GO por deuda mala.

Prestamista, liquidez, prima, swap, repago atómico, gas/reembolso, compensación incremental del builder, cobertura Titan Base/candidata, margen propio simulado, inclusión y beneficio realizado permanecen **null**. El patrocinio público de Titan es condicional; no acredita estas candidatas. No se extrapola la prima cero de Ethereum H24 ni el prior de otros liquidadores.

Contabilidad pendiente: salida del swap menos principal, prima, reembolso efectivo de gas y compensación incremental del builder, sin duplicar gas/propinas ya incluidos en el reembolso.

## Evidencia y límites

- [Datos finales congelados](https://github.com/josuechavando350-png/nexus-quant-capital/tree/e13cbcdfe39ae441259ddc4d2c514bee68dda52a/corridas/41722601722).
- [Auditoría final](evidence/titan-flash-final-20261103.json), incluidas identidades y causas de exclusión.
- [Entradas exactas](evidence/titan-flash-final-input.jsonl).
- Census 41572304605 conserva fallos Sei/Corn y rangos parciales; no se relanzó. Su evidencia previa queda en [control 1](evidence/titan-flash-slot1-20261103.json).
- 341 pruebas offline y aislamiento PASS en este control; no se atribuyen a CI del commit documental final. No se modifican código, run.json ni workflows. Sin firmas, operaciones ni fondos.
- Confianza alta en recuentos y reproducción aritmética; limitada en detección; rentabilidad no demostrada.

Antes de cualquier futura observación, la revisión pendiente es explicar los 44 casos fuera del libro y la falta de medición de trozos, además de acreditar financiación y economía. Este cierre no autoriza una extensión.
