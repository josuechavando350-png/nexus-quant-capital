# Auditoría H2 — integración offline de Census

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.
Base revisada: `36e948b01f1c9efdf6b6394cfa11adda01f18670`.

## Resultados ejecutados

- 43 pruebas de Omega aprobadas: 11 originales y 32 nuevas, sin errores ni skips
  cuando se suministran los dos ZIP auténticos. Incluyen seis pruebas con los
  archivos reales y una matriz de 1,440 mutaciones de campos de componentes.
- 15 pruebas originales de `test_rmc016_winner_net_audit.py` aprobadas. El archivo
  de pruebas y el auditor son byte-idénticos a los Git blobs recuperados.
- 58 pruebas en total en estas DOS suites; NO es la suite completa del repositorio.
- Replay del auditor original y del puente sin red, sin subprocess del puente,
  sin firma, sin gasto y sin RPC. La repetición produce el mismo reporte.
- Fuente PDF cotejada con SHA-256
  `5c1739799ab5099bc95f7347aeed8bcc2e3b098e64c3688584331004f15edf0f`.
- Compromiso del reporte original:
  `89ebe73a36127f0bfec5f722d5ca4ece0e7e15c8318d68f33f38eeff5ae6a5ca`.
- Compromiso del reporte Omega (excluye su propio campo de compromiso):
  `efb5583028daa7acbf7b8f949f68165ce18a3e9dccd9750dcf6fc166a0fbf0f0`.

## Identidad original preservada

Repositorio productor histórico: `josuechavando350-png/nexus-engine`, ID
`1333360261`. Repositorio consumidor: `josuechavando350-png/nexus-quant-capital`,
ID `1411047452`. No se transfieren certificaciones entre ambos.

| Entrada | Identidad comprobada |
|---|---|
| ZIP D15B, artefacto 11504276505 | SHA-256 `aff472236ff5177f123e4a6ccc95d4dae5fb37833f8645984116c407c179d790` |
| ZIP D16, artefacto 11505504820 | SHA-256 `27bd8909f865429e6bbc4580adf52af985beab8ed45cc11850616ab53a02b199` |
| Auditor RMC-016 | Git blob `fb0c6988edb30542c899e80c32c355e73e37dba2` |
| Fuente económica D16 | Git blob `5d5ed3635a426d686c8a98aa3547fd5b9d8b95aa` |
| Pruebas originales RMC-016 | Git blob `688eabf89c22ee8c15eed35dc3d50dce456816f7` |
| Verificador original de aislamiento | Git blob `3bb842872a4ca89e81bcf45839b42cc88d26f84e` |

Los ZIP se recuperaron por sus IDs originales y se comprobaron los hashes
externos y manifiestos internos. No se publica una copia de los ZIP en este PR.
Esto verifica identidad de bytes y coherencia de agregados; NO es una nueva
validación de productor CI, consenso, contratos ni ejecución EVM.

## Hallazgos y cambios

El verificador histórico permite únicamente las raíces del snapshot importado;
por ello rechaza `omega/`. No se debilitó ni editó. El adaptador nuevo aparta
solamente una lista cerrada de 11 archivos Omega en una copia temporal y ejecuta
el verificador ORIGINAL sobre todo lo demás. Sus pruebas comprueban que archivos
extraños, workflows y árboles de clientes NO se ocultan, que se preservan bytes
y modos, y que una copia incompleta no puede obtener PASS.

El auditor inicial del plan podía lanzar excepciones con IDs, capas, fases o
criterios de aceptación de tipo incorrecto. Ahora devuelve rechazo explícito;
la lectura también rechaza claves duplicadas, NaN e Infinity. Los límites de
Canary quedan comprobados como enteros: 2000 / 500 / 1000 MXN.

El puente conserva **127 transacciones ganadoras históricas y 139 eventos**,
limitados a Aave V3 Ethereum en bloques 25880316–26095351. No se recuentan eventos
como transacciones. El agregado no publica el ledger por transacción ni prueba
costos completos, retraso desde oráculo, propina al builder o rentabilidad de
NQC. Los campos no establecidos son `null`, no cero. Decisión: **OBSERVAR**;
Census y el avance de fase permanecen bloqueados.

## Bloqueos que NO se declaran aprobados

1. No se obtuvo un checkout completo: la descarga directa no tuvo acceso de red
   y la terminal conectada rechazó ejecución por cuota. Se recuperó únicamente
   el subconjunto necesario, autenticado por Git blob, y los ZIP indicados.
2. `omega/isolation.py` se intentó sobre esa copia parcial: devolvió
   `OMEGA_ISOLATION_BLOCKED`, salida 1, al faltar la copia local de
   `migration/source-manifest.json`. El archivo existe en GitHub; no se presenta
   este fallo local como un defecto del repositorio. Falta ejecutar el verificador
   sobre todos los archivos originales y su prueba con el almacén Git fuente.
3. No se ejecutaron la regresión Python completa, Rust, PFT/forks, paridad EVM,
   latencias reales ni adquisición de mercados actuales. No hay Cargo local.
4. No hay cierre de Census, certificación de los 36 componentes, captura real,
   beneficio propio demostrado ni autorización para pasar a Shadow/Canary.

## Medición del hito

Cuatro controles del hito H2: (1) recuperar y autenticar la evidencia histórica;
(2) integrar el puente y aprobar las pruebas acotadas; (3) publicar y verificar
los bytes en la rama; (4) aprobar aislamiento y regresión del repositorio completo.
Los controles 1 y 2 están aprobados en esta auditoría local. El control 3 requiere
read-back de GitHub; su resultado se registra en el PR. El control 4 sigue
pendiente. Máximo reportable después de publicar: **75% del hito H2**, no 75%
del sistema. Avance funcional certificado: **0/36 (0%)**.
