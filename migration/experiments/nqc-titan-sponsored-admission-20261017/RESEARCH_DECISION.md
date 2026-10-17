# Dictamen de investigación — Directiva 005

**PAUSAR la admisión comercial; CONTINUAR sólo la verificación documental acotada si aparece evidencia nueva.** Se refuta la variante donde el builder financia pero el reembolso se atribuye a un tercero. La variante alineada funciona en fixture y sigue MODEL_ONLY. No existe demostración de compatibilidad comercial ni de rentabilidad histórica de NQC.

## Evidencia económica nueva

| Escenario | Gas efectivo local | Caja builder ETH | WETH nuevo NQC | Dictamen |
|---|---:|---:|---:|---|
| V05, builder fondea; R al externo | 2,318,206 × 2 gwei | −0.004636412 | 0.159365645570551238 | REFUTED bajo estas condiciones |
| V06, builder fondea y recibe R/U | 2,318,206 × 2 gwei | +0.045363588 | 0.159365645570551238 | PASS_LOCAL; comercial UNKNOWN |
| V07, anticipo insuficiente | 21,000 × 2 gwei | −0.000052 | 0 | Sólo top-up incluido; 4 pendientes |

V05 y V06 tienen idénticos mercado, deuda, reservas, gas y saldos iniciales NQC. Sólo se cambia destinatario de R. En V05 el tercero recibe 0.05 ETH: ese dinero no es del builder. En V06 builder y financiador son la **misma dirección asignada de laboratorio**, no dos cuentas cuya propiedad real se presume. El proponente permanece separado.

V06: A=30,000,000,000,000,000 wei; R=50,000,000,000,000,000; U=25,405,588,000,000,000 efectivamente devueltos; F=42,000,000,000,000; V=P=O=0 en caja del financiador. `R+U−A−F=45,363,588,000,000,000`. El gas de NQC de 4,594,412,000,000,000 ya está incluido en A−U: no se resta otra vez. El tip de 0.04 ETH ya salió del colateral convertido dentro de la liquidación; no es otro gasto directo del builder. Priority fees se pagan al proponente; nunca se le suman al builder.

La conversión sintética genera 8.249365645570551238 WETH, repaga 8 WETH y convierte 0.09 WETH en 0.05 ETH de R más 0.04 ETH de tip. Quedan 0.159365645570551238 WETH. No se suman a la caja ETH. Esto no usa la operación histórica B ni el DEX Fluid. El builder posee 100 ETH de fixture; se demuestra cero capital inicial **NQC**, no disponibilidad comercial de capital externo.

Frente al conjunto declarado sponsor+builder de 004 se elimina una transferencia interna de 21,000 gas: ahorro real de 42,000,000,000,000 wei a 2 gwei. No se elimina por aritmética el costo de una transferencia que sí se ejecutó: V06 ejecuta cinco transacciones y 004 ejecutó seis.

## Regresión por titular, no por etiqueta

| 004 rederivada | Sponsor distinto | Builder distinto | Conjunto si propiedad común explícita |
|---|---:|---:|---:|
| 2 gwei | +0.043321588 ETH | +0.002 ETH | +0.045321588 ETH |
| 21 gwei | −0.001123326 ETH | +0.002 ETH | +0.000876674 ETH |

El costo ilustrativo de capital es 1bp de A: 0.000003/0.00003 ETH respectivamente; no tarifa de proveedor. La pérdida del sponsor separado a 21 gwei no queda corregida atribuyéndole otra cuenta sin prueba. C2 no se amplió; conserva los resultados y restricciones de liquidez documentados en 004.

## Frontera adicional exacta

Para V06 con G=2,318,206 gas, caps=precio efectivo f y mínimo anticipo `A=4,411,179*f`:

`margen = 50,000,000,000,000,000 − G*f − ceil(A/10000)`.

Último f positivo: **21,564,299,118 wei/gas**, margen **515,787 wei**, A **95,123,983,419,040,122 wei**. Al siguiente wei/gas: **−1,802,860 wei**. Conservar A=0.03 ETH limita primero la reserva de prefijos a **6,800,902,887 wei/gas**, aunque el margen aritmético todavía sea positivo. No confundir precio rentable con capital financiable.

Si se añaden 10,000/100,000 gas antes del prefijo limitante, los cortes calculados caen a 21,471,685,488 / 20,672,628,472 wei/gas. Sensibilidad matemática de G/K, **no nuevas ejecuciones EVM**, no estimación de precio de inclusión. Costos externos y gas real variable pueden reducirlos más. La frontera no demuestra un margen histórico capturable.

## G0–G5

| Criterio | Cambio aportado | Estado comercial |
|---|---|---|
| G0 sin recurso personal | null se propaga; obligación hipotética positiva rechaza | UNKNOWN |
| G1 estado auténtico | No se usó fixture como caso B | BLOCKED_PRESTATE |
| G2 sponsor real/suficiente | Mapeo por titular y tres trazas nuevas; receptor real null | BLOCKED_EXTERNAL_EVIDENCE |
| G3 neto NQC tras obligaciones | Caja y activos reconciliados por actor; no costo desconocido=0 | UNKNOWN |
| G4 disponibilidad antes de cutoff | No se generó nueva evidencia temporal | UNKNOWN |
| G5 recurrencia/captura | Sin nuevas probabilidades ni censo | NO ESTIMABLE |

## Decisión y próxima prueba

DESCARTAR V05 para patrocinio que exige incremento del builder bajo los costos probados. Mantener V06 sólo como intención condicionada. Aplicar la prueba documental única de ADMISSION_AND_NO_RECOURSE_GAPS.md; detener repeticiones sintéticas sin esa evidencia. No hay autorización de envío, firmas o pruebas de producción.

Resultado cualitativo: avance técnico útil con refutación concreta, comercialmente no demostrado. Motivación técnica **7/10**; confianza comercial **2/10**, valoración cualitativa, no probabilidad. P&L realizado certificado NQC **US$0**. Potencial mensual **NO ESTIMABLE**.
