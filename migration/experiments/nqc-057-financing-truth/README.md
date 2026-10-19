# NQC057 — FINANCING TRUTH

**FINANCING_DOCUMENTATION_BOUNDARY_REACHED. Financiación real NO confirmada.** No tenemos un financiador comprometido con NQC ni evidencia aplicable de ausencia de recurso personal. `commercial_admission=false`. La investigación se detiene en este límite; no se enviaron bundles, solicitudes de aceptación ni contactos comerciales.

Rama `research/nqc-057-financing-truth-20261019`, padre directo `2eb07985e5c20e053a5e06b7c0a67cd5a629cb60`. Las 82 ramas remotas se revisaron antes de escribir; NQC056 seguía siendo la última continuación. Todos los archivos añadidos pertenecen a este experimento.

## Respuestas decisivas

1. **Principal Morpho:** sí puede evitarse adelantar toda la deuda mediante colateral → venta en callback → repago, bajo condiciones técnicas verificadas en laboratorio con el código original fijado. La venta debe entregar suficiente activo de deuda y cubrir las demás asignaciones. Esto no autentica preestado, venta ni captura de los candidatos históricos.
2. **Gas:** Titan y Quasar mantienen documentación de patrocinio condicional. La diferencia de cobertura y sus límites están abajo. Documentar una función no constituye oferta ni compromiso con NQC.
3. **Aceptación pendiente:** faltan identidad/titularidad del financiador y receptores, monto/timing del anticipo, caps por prefijo, CREATE/inicialización, devolución de sobrantes, economía neta tras pagar al proponente, manejo de fallos, y aceptación de la secuencia concreta. No basta aprobar una simulación.
4. **Pérdidas y recurso:** el libro identifica pérdidas de caja locales por dirección; no identifica al obligado contractual en producción. Garantías personales, deuda residual, cobros diferidos y responsabilidad por fallos: **UNKNOWN**. El silencio documental no demuestra ausencia de recurso.
5. **¿Financiador real comprometido? NO.** Ninguna fila recibe `SPECIFIC_PROVIDER_ACCEPTANCE_VERIFIED`. No se afirma `FINANCING_SECURED`.
6. **Evidencia mínima que cambia la decisión:** reglas verificables aplicables al mecanismo concreto sobre fondos, importes, destinatarios, devolución, pérdidas y ausencia de recurso; después evidencia específica de aceptación y fondeo, vinculada a una oportunidad auténtica. Puede ser un programa público verificable; no se exige por definición negociación privada. Nada de eso se solicitó o autorizó aquí.

## Contraste público acotado

Ocho páginas oficiales fueron legibles el 2026-10-19. `PUBLIC_REVIEW.json` conserva URLs, secciones, fecha de consulta y fragmentos mínimos. No se preserva ni se atribuye un hash al cuerpo HTTP completo. Se mantienen hashes de este registro de revisión. Los dos índices `llms.txt` devolvieron errores del lector y no se reintentaron; no se presenta la búsqueda como examen exhaustivo de todos los términos existentes.

Fuentes: [Titan API](https://docs.titanbuilder.xyz/api/eth_sendbundle) (T_API), [artículo oficial enlazado, 2023-07-03](https://titanbuilder.substack.com/p/titan-tech-teatime-1) (T_ARTICLE), [Titan general](https://docs.titanbuilder.xyz/) (T_GENERAL), [Titan tracing](https://docs.titanbuilder.xyz/bundle-tracing) (T_TRACE); [Quasar API](https://docs.quasar.win/api/eth_sendbundle) (Q_API), [general](https://docs.quasar.win/) (Q_GENERAL), [tracing](https://docs.quasar.win/bundle-tracing) (Q_TRACE), [autenticación](https://docs.quasar.win/authentication) (Q_AUTH). Se leyeron páginas; no se llamó a sus endpoints RPC/estadísticas.

| Aspecto exigido | Titan | Quasar |
|---|---|---|
| 1. Tipo documentado | Adelanto ETH condicionado a `LackOfFundForGasLimit` | Mismo disparador documentado |
| 2. Gas | Cobertura descrita | Cobertura descrita |
| 3. Value / principal | Incluye ETH value; no línea ERC20 incondicional | Value/principal UNKNOWN |
| 4. Adelanto | Artículo describe simulación y transferencia antepuesta | Monto, orden y capacidad concretos UNKNOWN |
| 5. Exigencia económica | Recuperar patrocinio y aumentar balance builder | Recuperar patrocinio y aumentar balance builder |
| 6. Firmas | `txs` firmadas por sus remitentes | `txs` firmadas por sus remitentes |
| 7. Refund API | 0–99%; receptor configurable; insuficiencia para gas de refund descarta; selector ambiguo | 0–99%; receptor configurable; base textual total frente a selector de una tx requiere aclaración |
| 8. Revert/drop | Lista revert permite revertir/descartar; lista drop solo descartar | Lista revert permite revertir; lista drop solo descartar |
| 9. No inclusión | Simulación/Submitted no garantizan bloque ganador | Selección/Submitted no garantizan aterrizaje canónico |
| 10. Inclusión parcial | General afirma no separar bundles; no es prueba de atomicidad EVM entre transacciones | API denomina conjunto atómico; garantías concretas ante parcialidad UNKNOWN |
| 11. Gas, omisiones, reorg | Obligaciones/indemnización específicas UNKNOWN | Obligaciones/indemnización específicas UNKNOWN |
| 12. Quién pierde | Recurso y distribución contractual UNKNOWN | Recurso y distribución contractual UNKNOWN |
| 13. CREATE / inicialización / múltiples operaciones | Cobertura de la secuencia exacta UNKNOWN | Cobertura de la secuencia exacta UNKNOWN |
| 14. Compatibilidad NQC | Condicional; faltan campos de la respuesta 3 | Condicional; además falta cobertura value si se requiere |

Las celdas 1–8 contrastan T_API/Q_API con el expediente original `titan_spec`; 4 usa T_ARTICLE; 9 usa T_TRACE/Q_TRACE; 10 distingue T_GENERAL de la inferencia EVM propia. Las celdas UNKNOWN señalan ausencia de prueba en el alcance leído, no una política privada inventada.

T_TRACE explicita rechazo con incremento neto builder no positivo. El criterio exacto sobre todos los pagos/costes de una secuencia NQC sigue sin verificarse. Q_TRACE distingue etapas de simulación, selección, envío y aterrizaje; un hash de bundle no acredita fondeo ni beneficio. Q_AUTH describe prioridad opcional por firma/reputación; no convierte autenticación en financiación. No se usaron firmas ni credenciales.

El contexto investigado es Ethereum; no se ha probado aceptación del chain ID 1 para NQC ni se extrapola a Robinhood 4663 o al laboratorio 31337. Accesibilidad de documentación no acredita disponibilidad operativa actual. No apareció una nueva garantía decisiva frente a `titan_spec` y NQC023: **revalidación documental, no cambio de estado comercial**.

## Tres problemas económicos separados

**A — Principal.** En Morpho upstream `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`, el colateral se transfiere antes del callback opcional y se cobra `repaidAssets` después. Los expedientes C1 ya ejecutaron esa ruta con cash Morpho cero. NQC056 conserva el límite de vinculación con runtime/preestado histórico; no se repite su prueba. Ningún flujo de esa llamada crea automáticamente un préstamo comercial a NQC. La financiación del gas permanece separada.

**B — Gas y preparación.** El pagador necesita fondos y reservas máximas suficientes en cada prefijo, incluidos CREATE y retornos. El gasto efectivo no es la suma de todos los caps. Un retorno U firmado para cierto anticipo/precio puede fallar con otro: NQC018 demostró re-cotización cuando el adelanto ya es conocido, no una solución a importes desconocidos después de fijar las instrucciones. Hay que conocer el anticipo y devolución o verificar un mecanismo acotado de liquidación de obligaciones. No se inventó ese mecanismo para un proveedor real.

**C — Flash/external.** El `flashLoan` original entrega `assets`, llama al callback y recupera exactamente `assets`; esa versión no añade una prima en el core. No significa coste total cero ni disponibilidad real. Hace falta saldo transferible suficiente del token en el contrato y repago atómico; de lo contrario revierte la llamada y persiste el gas de la transacción. C2 heredado usó 8 WETH y falló con cash cero o inferior; la liquidación y el flash tienen obligaciones distintas. Sus despliegues originales consumieron más gas en el primer ciclo que C1. No se recomienda reconstruir el adaptador deprecado ni suponer infraestructura predesplegada gratuita. Préstamos/financiadores externos distintos: sin oferta, prima, colateral o términos reales acreditados.

La matriz máquina `FINANCING_MATRIX.json` incluye seis mecanismos, cadena/alcance, gas, value, capital previo, reembolsos, participantes, fallos, inclusión, recurso, fuentes y bloqueos. Estado público, validación de modelo y términos comerciales son dimensiones distintas; ningún estado documental habilita operaciones.

## Evidencia técnica reutilizada y reconciliada

`SOURCE_MANIFEST.json` fija **27 fuentes por commit, blob Git y SHA256**, incluyendo los cinco expedientes solicitados, NQC053–056 y la continuación relevante NQC023. `audit.py` coteja cinco casos ya conservados con sus snapshots, recibos y extracción de flujos publicada. No vuelve a ejecutar contratos, redecodificar todas las trazas ni certificar estado mainnet.

| Caso conservado | Caja financiador ETH | Caja builder ETH | Residuo operador WETH | Resultado acotado |
|---|---:|---:|---:|---|
| A2_C1_zero_cash | 0.043321588 | 0.002 | 0.159365645570551238 | Modelo local favorable |
| A2_C1_high_gas | -0.001123326 | 0.002 | 0.159365645570551238 | Rechazado para financiador separado |
| V05 | -0.004636412 | Misma dirección: no sumar | 0.159365645570551238 | Rechazado con R destinado al tercero |
| V06 | 0.045363588 | Misma dirección: no sumar | 0.159365645570551238 | Modelo local favorable; costes externos UNKNOWN |
| V07 | -0.000052 | Misma dirección: no sumar | 0 | Camino incompleto; anticipo retenido no es beneficio |

Los importes son de laboratorio y no pronostican ingresos. En los cinco casos el gas real y el saldo se separan por activo/dirección; tokens y ETH nunca se agregan. El financiador aporta capital sintético externo. El libro completo y referencias están en `evidence/reconciliation.json`; las obligaciones por actor y fallos están en `PARTICIPANTS.md`.

**Continuación que no debe perderse:** NQC023 ya auditó exportaciones de NQC021. Su informe fijado registra `net_050`: builder +0.042398012 ETH antes del pago separado al proponente, **-0.000091398 ETH después**. El avance positivo intermedio tampoco es beneficio final. Este turno verifica el hash y lee ese informe; no recupera de nuevo sus 77 archivos ni presenta sus 52 recibos como auditados aquí. NQC018/NQC023 son resúmenes de ejecuciones previas con su procedencia y limitaciones originales.

NQC054 solo descartó financiar toda la deuda del caso histórico B con prima >=1 bp manteniendo venta/puja observadas. No se extiende ese descarte a todo Morpho, a la ruta C1 ni a pufETH. NQC056 mantiene pufETH sin recibo/preestado/contabilidad auténticos; patrocinio documental no resuelve ese bloqueo. No hay beneficio capturado por NQC ni pronóstico sustentado de USD 5.000–45.000 mensuales.

## Decisión y siguiente movimiento

Mantener **C1 colateral-primero + gas externo** como hipótesis técnica preferida para evitar principal, porque el modelo conservado reduce la dependencia de cash de préstamo. Esa preferencia no es ranking de rentabilidad real. Titan y Quasar permanecen candidatos documentales; **suspender pruebas operativas y simulaciones equivalentes** hasta que exista evidencia adicional aplicable. No se justifica añadir otro prestamista sin resolver el gas y la contabilidad de una oportunidad auténtica.

El siguiente movimiento de mayor impacto es reunir **un único expediente aplicable a una secuencia concreta** que identifique anticipo y receptores, cobertura CREATE/caps/value, retorno, remuneración builder/proposer y asignación de pérdidas sin recurso personal. Antes de ejecutar harían falta oportunidad auténtica y aceptación/fondeo específico bajo nueva autorización. Si ese expediente no es públicamente accesible, el límite permanece; no se contactará a nadie ni se pedirá al propietario Android ejecutar terminales, firmar o depositar fondos. El valor informativo propuesto depende de que esa evidencia exista y sea verificable; no se le asigna probabilidad ni ganancia esperada.

## Reproducción y límites de validación

```sh
PYTHONDONTWRITEBYTECODE=1 python migration/experiments/nqc-057-financing-truth/run_checks.py
```

Checkout íntegro con los commits del manifiesto, Python estándar y Git. Sin instalación ni red. Regenera libro y logs; los tiempos/rutas de logs pueden variar. La clasificación pública es revisión humana respaldada por fuentes, no una verificación automática del operador.

Pruebas pertinentes: **8 nuevas + 9 de aislamiento**, cero escenarios EVM nuevos. `VALIDATION.json` y logs contienen resultados exactos. Se registran el error inicial de inspección de metadatos (lista leída como objeto), corregido sin tocar fuentes, y los dos índices web inaccesibles. No se repiten suites equivalentes, Rust/Solidity ni exportaciones CI. Aislamiento no equivale a recertificación global.

Seguridad: sin contactos, ofertas privadas, cuentas, suscripciones, aceptación contractual, fondos, firmas, bundles, despliegues, RPC ni subagentes. Triport: **0 consumidas conocidas / 8 vitalicias**, registro único y canal seguro pendientes. El presupuesto propio futuro de gas sigue limitado a 2.000 MXN desde Canary, recargas <=500 MXN y revisión al agotar 1.000 MXN sin captura; no disponible ahora. Sin capital principal ni fondos en carteras Census/Shadow. `main`, fuentes previas e integraciones permanecen intactos.
