# Continuación: causas de exclusión y cobertura real

## Resultado comprobado

El acumulado anterior a Shadow v12 reúne 14 corridas y aproximadamente 28.8 h.
La auditoría de sus siete liquidaciones explica por qué ninguna entra en la
muestra. No se han rebajado los criterios ni convertido bonos de terceros en
ganancias propias.

| Filtro consecutivo | Casos restantes | Bono bruto de terceros |
| --- | ---: | ---: |
| Observadas tras deduplicación | 7 | USD 196.505855 |
| Vía directa | 5 | USD 30.754942 |
| Bono de al menos USD 1 | 1 | USD 30.606396 |
| Ganador en un trozo posterior medido | 0 | USD 0 |
| Tiempos con origen común e integridad | 0 | USD 0 |

Dos liquidaciones fueron por subasta. Cuatro directas tuvieron bonos inferiores
a USD 1. La única directa mayor llegó en el mismo trozo de Flashblocks que la
actualización del oráculo. La falta de tiempos en registros antiguos existe,
pero no explica por sí sola el 0/20: ninguno supera los filtros anteriores.

El nuevo `embudo_muestra` del acumulador presenta estos filtros y la primera
causa de exclusión por evento. Conserva casos con holgura negativa; no sustituye
tiempos por medianas y no cambia el criterio de admisión. La corrida v12 activa
no se mezcla con este diagnóstico histórico.

Entradas retenidas y resultados: [audit.json](evidence/continuation-20261103/audit.json).
Incluye SHA-256, rutas de origen y las cuatro corridas que contienen las siete
liquidaciones. No es una nueva recomputación de toda la cobertura temporal.

## Recuperación Census v12

Fuente: run `41572304605`, productor `259a796ee96433c4fea1c026b4040440aa644234`.
Ventana: 25 septiembre–25 octubre de 2026. Cobertura por bloques, no proporción
de oportunidades ni porcentaje global de finalización de NQC.

| Cadena | Cobertura de bloques | Eventos encontrados | Resultado |
| --- | ---: | ---: | --- |
| Soneium | 100% | 0 | Ventana completa |
| Gensyn | 91.9367% | 0 | Presupuesto agotado; faltan 104,500 bloques |
| Cronos | 63.1110% | 0 | Presupuesto agotado; faltan 2,191,644 bloques |
| Monad | 13.7182% | 0 | Presupuesto agotado; faltan 7,400,042 bloques |
| Flare | 10.3863% | 22 | Presupuesto agotado; faltan 2,096,622 bloques |
| Sei | Sin ventana resuelta | Desconocido | Historia podada |
| Corn | Sin ventana resuelta | Desconocido | Proveedor indisponible |
| HyperEVM | Pendiente al corte | Pendiente | Job todavía activo |

Los 22 eventos de Flare se recuperaron como prefijo histórico. No acreditan
costes, rentabilidad ni casos de la muestra prospectiva de Base.

### Correcciones derivadas de los resultados

Gensyn, Cronos y Monad registraron una excepción de presupuesto agotado en
`errors_sample`, pero escribieron `time_budget_hit=false`. El código ahora:

- marca el agotamiento global en consultas de eventos;
- conserva logs y último bloque cubierto, identificando el primer bloque ausente;
- registra el tramo incompleto como fallo y evita iniciar enriquecimiento posterior;
- distingue un subpresupuesto de oráculos del presupuesto global;
- exige `events_complete=true` para preferir una corrida al seleccionar tramos.
  Un job SUCCESS parcial ya no desplaza una cobertura completa.

No se reescribe evidencia histórica. Los flags contradictorios originales quedan
retenidos. La corrección solo afecta productores futuros; el workflow activo usa
su commit fijado. Sin cambios en workflows ni en run.json.

## Financiación

La política permanece Titan para gas y préstamos flash para principal, con
aportación propia cero. La documentación oficial de
[Morpho Blue](https://docs.morpho.org/developers/contracts/blue/) describe prima
flash cero y un límite basado en el saldo del contrato; esto no prueba liquidez
ni identidad del código en el bloque de una candidata. La
[documentación de Titan](https://docs.titanbuilder.xyz/api/eth_sendbundle) requiere
recuperar el patrocinio con la ejecución. No se ha verificado cobertura específica
de Titan para Base ni una aceptación de bundle NQC.

El intento de iniciar una consulta independiente por Blockscout terminó en timeout
del conector. No produjo un recibo, traza o dato de financiación nuevo. Por tanto,
no se avanza la afirmación de rentabilidad ni se modifica la evidencia H24.

## Validación y siguiente paso

341 pruebas Python offline: OK. Regresiones de presupuesto, conservación del
prefijo, selección de cobertura completa y diagnóstico de la muestra. Verificación
de aislamiento: PASS; no recertifica los objetos originales. No se ejecutaron
pruebas Rust/Solidity, porque este cambio es Python y no modifica esos componentes.

Dejar terminar Shadow v12 y HyperEVM; usar las revisiones ya programadas para
continuar las ventanas autorizadas con el nuevo productor. Antes de repetir
Census, preparar tramos que cubran las partes faltantes y verificar que el reporte
las combine sin huecos ni solapamientos. No volver a escanear a ciegas los mismos
prefijos ni presentar la ausencia de eventos en un prefijo como cero en 30 días.
