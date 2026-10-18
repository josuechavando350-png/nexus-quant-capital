# NQC 666 — Tercer Ojo, Cerebros, Cazadores y Guardianes

## Alcance y fronteras

Un motor Rust determinista de laboratorio, un propietario del estado y hasta 256
posiciones registradas. Cero procesos/agentes auxiliares, workers, RPC, firma,
wallets, envío o autorización comercial. Cero dependencias de Cargo. El C++ se
conserva exclusivamente como baseline original; no se añadió una extensión C++,
ASM o SIMD al motor. Las instrucciones de reloj/caché pertenecen al instrumento.

Es una integración LOCAL sobre entradas decodificadas sintéticas. **No hay todavía
adaptador Morpho U256/IRM, prueba de estado, cotizador, simulador EVM ni builder.**
Por ello la decisión económica completa de una liquidación real y los niveles de
recepción de red y extremo a extremo permanecen NO MEDIDOS. El modelo económico
completo de NQC019 sí se ejecuta y conserva sus resultados exactos.

Flujo: actualización completa del slot → comprobación de identidad → generación
nueva → clasificación y escenarios → control financiero y guardianes → prioridad
incremental → ticket con generación → verificación financiera y defensiva FINAL.
El ticket no es una transacción, firma ni permiso. No existe API de ejecución.

## Dieciocho responsabilidades, no dieciocho servicios

| Grupo | Rol | Implementación y límite |
|---|---|---|
| Cerebro 1 | Estado del protocolo | `Engine`, `Key`, `Anchor`, generaciones; un bloque/hash único. Sin lectura de cadena. |
| Cerebro 2 | Economía | `financial::screen_at`, aritmética u128 comprobada, equivalencia NQC019. Cotización y conversión suministradas, no calculadas. |
| Cerebro 3 | Oportunidades | Árbol de torneo, 256 slots, empate por índice menor. Sin catálogo de mercados real. |
| Cerebro 4 | Gas e inclusión | Reserva máxima versus coste observado, probabilidad explícita opcional. Sin modelo aprendido ni garantía de inclusión. |
| Cerebro 5 | Predicción | `third_eye::assess`; bandas de interés/capacidad condicionales. No interpreta estimaciones como observaciones. |
| Cerebro 6 | Coordinación | Propietario único, préstamo inmutable Rust durante cada evaluación; generación invalida tickets antiguos. |
| Cazador 1 | Proximidad | Margen contra máximo de deuda; igualdad sana; umbral de proximidad configurable en bps. |
| Cazador 2 | Oráculo | Nuevo snapshot y caducidad invalidan candidatos. Feed auténtico pendiente. |
| Cazador 3 | Deuda | Recálculo por actualización del slot; redondeo Morpho debe venir del futuro adaptador. |
| Cazador 4 | Colateral | Actualización de `max_borrow`; sin reconstrucción autónoma desde logs. |
| Cazador 5 | Transacciones pendientes | **No implementado**: no hay feed ni evidencia de cobertura. No añadir un proceso decorativo. |
| Cazador 6 | Prioridad | Valor esperado conservador con probabilidad y pérdida explícitas; desconocido/overflow/margen no positivo excluidos. |
| Guardián 1 | Datos | Cadena, bloque, hash, índices, claves registradas, generación y fechas; comparación local, sin autenticación criptográfica. |
| Guardián 2 | Contratos | Comparación de code hash y presencia de plan hash. No demuestra bytecode seguro, binding ABI ni ejecución EVM. |
| Guardián 3 | Gas/fondeo | Límites, prefijos de caja, cap, reserva del financiador y capital propio cero. Condiciones desconocidas bloquean clasificación local. |
| Guardián 4 | Ejecución | Nonces contiguos del operador, dependencias anteriores y máscara de éxito suministrada. No decodifica un bundle multisender. |
| Guardián 5 | Pagos | Reembolso/financiación, builder, proponente, sobrante y costes en el modelo; sin recibos originales nuevos. |
| Guardián 6 | Neto | Márgenes del operador/financiador, neto inferior declarado y slippage; `commercial_admission=false` siempre. |

## Precomputación útil y sus invariantes

`Prepared` sólo nace tras aprobar el screen completo. Su forma de referencia
ocupa 32 bytes. `Compact` ocupa 24: elimina el campo privado `ready=1`, que era
invariable después del constructor, conservando generación y ambos límites
temporales. Nadie puede construir sus campos mediante una API pública segura.

El filtro responde exclusivamente: «¿sigue temporalmente utilizable este
precontrol ya preparado para esta generación?». **No responde** «¿es rentable o
autorizada la operación actual?». Prepararlo cuesta el screen completo; ese coste
se mide aparte y dentro de la canalización. Un cambio económico requiere una
actualización completa y una nueva generación, no modificar un campo fuera del
motor. Las entradas se guardan por valor: no hay punteros externos mutables.

La ventana incluye edad máxima y tiempo de envío reservado, con comprobación
de overflow y límites inclusivos/exclusivos explícitos. Oráculo y ruta también
deben seguir vigentes durante todo ese presupuesto. El filtro no sustituye
`finalize`: éste vuelve a ejecutar finanzas y guardianes sobre el estado actual.

## Estado coherente y actualización incremental

Una actualización cambia un slot y ocho nodos ancestros del torneo: O(log 256).
La selección normal lee la raíz. Expirar muchos líderes puede costar hasta
O(256 log 256): el límite se declara, no se esconde tras un benchmark favorable.
Cambio de bloque o reorg invalida todos los slots, O(256), por seguridad; aquí no
se presume continuidad de un snapshot anterior. Un evento inválido sobre un slot
existente lo invalida antes de devolver error. Las generaciones no se reutilizan
al regresar a un hash antiguo y su agotamiento se rechaza.

Inicialización: dos vectores acotados. Ruta de eventos: estructuras de tamaño fijo,
sin asignaciones por evento, locks, colas o serialización. El fixture de entrada
se copia al transferir propiedad al motor; la mejora `screen_at` elimina otra copia
completa que sólo se hacía para sustituir `now_ns` en el control defensivo.

## Tercer Ojo: datos, inferencias y predicciones

`Basis::SyntheticFixture` etiqueta cada escenario de laboratorio. `Basis::Unknown`
fuerza `Observed::Unknown`, aunque se suministren números. No hay variante
«mercado autenticado» disponible hasta implementar y validar un adaptador.
Los campos `debt` y `max_borrow` usan las MISMAS unidades atómicas de activo de
préstamo, y se supone que ya incluyen los redondeos exactos y el interés observado.
No se los convierte silenciosamente desde u256 ni se mezcla valor de tokens.

En Morpho, el contrato compara deuda redondeada al alza con capacidad redondeada
a la baja; igualdad no liquida. El experimento aplica esa comparación a sus
entradas, pero **no reproduce** el cálculo completo de shares, oráculo, LLTV o IRM.
Fuente primaria consultada: [Morpho.sol, health check e interest management](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol).
No es un pin de despliegue ni prueba de paridad contractual.

Las bandas de interés y capacidad futura son hipótesis suministradas con una
ventana temporal. Se distingue «puede cruzar», «cruza bajo estos supuestos» y
«permanece sano». Una banda ausente, incoherente, caducada o con overflow produce
predicción desconocida. Ninguna de ellas cambia `Observed` ni habilita ranking.
El valor esperado usa probabilidad de inclusión y pérdida por fallo declaradas;
si faltan, no inventa probabilidades. Redondea ingreso a la baja y pérdida al alza.

## Protecciones y autorización externa

Los bits del NQC019, hashes, éxito simulado, neto y condiciones son afirmaciones
de entrada, no demostraciones. Un valor `Some(true)` en fixtures no acredita un
contrato de financiación sin recurso. No hay operación comercialmente admisible,
incluso si `FinalCheck.reasons==0`. La interfaz lo declara explícitamente.

Para conectar datos reales será necesario un adaptador verificado que vincule
mercado/borrower/plan, activo/unidades, estado canónico, timestamp, todos los
firmantes y nonces, calldata, recibos/simulación, términos vigentes, destino del
sobrante y pagos. El estado del financiador y la ausencia de recurso personal
pertenecen a NQC031/032. Este trabajo sólo define la interfaz y rechaza lo desconocido.

## Inventario de los 350 agentes

Se localizó dentro de NQC la auditoría
`migration/audits/CROSS_REPO_EVIDENCE_2026-10-17.md` del commit
`6b3210a1ee73b5dd46eac7a728d6ed484276c3ac`, blob
`957cf17f82ddbc241f9074af561514bd2db24610`. Se conserva copia byte-idéntica
en `historical/NQC_AUDIT_350.md`.

La auditoría registra **48 roles en ocho mesas y 350 identidades PLANIFICADAS**,
`ARCHITECTURE_ONLY`, remitiendo a un contrato del repositorio original. El contrato
original no está en los objetos/rutas localizados de este clon de NQC; no se
accedió al repositorio excluido. Por tanto no se reenumeraron independientemente
sus 350 identidades. No existe aquí prueba de 350 agentes activos, y no se crean.
T37 sí conserva un harness de 256 shards y un ensayo sintético de 50.000 mercados;
no son 350 agentes ni prueba de cobertura real. No se inspeccionó runtime remoto.

## Hardware y técnicas descartadas o aplazadas

- Afinidad: sólo a una CPU ya permitida. No se modifican interrupciones, governor,
  turbo, kernel, permisos ni servicios. Un NUMA virtual reportado no prueba topología física.
- LTO/native/PGO: comparar resultados archivados; sólo recomendar una configuración
  si mejora este ensayo. PGO sintético no garantiza representatividad de producción.
- SIMD: no se implementa sin beneficio demostrado; los prefijos financieros
  tienen dependencias secuenciales y checks de overflow. El compilador puede
  vectorizar comparaciones de hashes; no se atribuye una mejora a SIMD sin aislarla.
- ASM/C++ adicional: rechazado como complejidad no justificada. C++ sólo baseline.
- FPGA: estudio de viabilidad, no hardware disponible ni compra. Un pipeline
  de comparadores podría tener throughput de un dato por ciclo después de llenarse,
  pero eso no equivale a latencia de datos de mercado→decisión→builder. Coste de
  transferencia, validación, herramienta y operación contradice una adopción sin
  evidencia y presupuesto. No afirmar imposibilidad física de 5 ns.
- Núcleo dedicado/NUMA/IRQ: siguiente experimento posible si hay acceso autorizado
  a hardware existente. La VM compartida actual no permite garantías de cola.
