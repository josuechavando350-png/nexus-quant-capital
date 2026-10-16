# Seis controles locales completados; admisión completa pendiente

Captura única del 16/oct/2026 **16:55:47.080760–16:55:50.559334 UTC**.
Protocolo publicado antes: `4a814940a80d3b5f6effced72984d3ffc53f6f5d`;
árbol `52d88bfe806b4984d3b14e4da079f37bff3ebc2c`. Sus 35 fuentes siguen intactas.
PR25, primer incremento del presupuesto de dos aceptado por Chavando.

La corrección elimina la causa local de PR24: el saldo de ecrecover se conserva
en genesis y su implementación nativa queda activa. No se cambian contratos ni
firma original. El control negativo cambia sólo 65 bytes de firma por ceros.

| Control fijado | Resultado observado |
|---|---|
| Firma original, 31 s, stake 0 | RETURN; firma válida; acceso al presupuesto del paymaster |
| Firma inválida | AA23/ECDSAInvalidSignature; paymaster no alcanzado |
| Firma original, 31 s, stake 1 ETH de laboratorio | RETURN; stake/delay devueltos conforme al fixture |
| Firma original, 1 s, stake de laboratorio | RETURN; devuelve exactamente 1 s de ventana |
| Depósito 0 | `AA31 paymaster deposit too low` |
| Presupuesto 0 | `AA33 reverted`, interior `BUDGET_POLICY` |

Los seis controles satisfacen las expectativas preregistradas: tres validaciones
positivas y tres rechazos esperados. No fueron seis oportunidades de mercado.
La precompilación nativa consume 3000 gas en firma positiva y negativa; recupera la
dirección pública de prueba `0xcf03dd0a894ef79cb5b601a43c4b25e3ae4c67ed` en las tres
positivas, y devuelve vacío para firma inválida. AccountValidationData=0 en positivas.
No firmas nuevas ni sustitución de ecrecover.

Cada retorno positivo exige prefund de 249541240000000 wei, contexto paymaster vacío,
y registra dos SLOAD y una SSTORE del presupuesto en slot 1. Stake observado de 0/1 ETH/1 ETH
y delay de 0/86400/86400 s son **estado impuesto por el laboratorio**. No fondos obtenidos,
stake mínimo comercial ni cotización. PreOpGas de 132658 en cada positivo corresponde
a validación local; no es gas del ciclo completo, Nitro/DA o precio comercial.

## Medición, auditoría y preservación

- 10 métodos RPC/10 HTTP locales;0 RPC públicos, 0 envíos; salida 0.
- Proceso 3.481232384 s, último retorno del journal a 3.463859016 s desde inicio.
- Esperas 1.860784101 s incluidas; gap mínimo 350.112459 ms; cero infracciones.
- Mismo hash/stateRoot de genesis antes/después:
  `0x576ad8d0b04db44b548b924210a0d70a6a295b423067a3023b29005b6c2d9350`.
- Geth detenido al finalizar. No se publican base de datos, clave de nodo ni JWT local.

`audit_native.py` verifica cuerpos/hash, orden, estado inicial, calldata/firma,
trazador, retornos ABI, errores negativos estrictos y resultado reproducido exacto.
`evidence/audit.json` es el informe derivado; los originales están en `evidence/pilot`.
No se alteró el runner, protocolo o lock después de medir.

48 pruebas Python distintas aprobadas: 14 nuevas antes de capturar (incluyen diez
fronteras RPC sintéticas interrumpidas), 5 de auditoría después, 20 regresiones de PR24 y 9 de aislamiento.
20 manifiestos previos y 35 fuentes fijadas intactos; 377 blobs originales;
106 workflows deshabilitados, 0 activos. Sin cambio/compilación de contratos NQC ni
nueva ejecución Solidity/Rust. Se reutiliza EntryPointSimulations compilado en PR24.
Logs de Geth originales contienen espacios finales: conservarlos aunque
`git diff --check` los señale; no son cambios de código propio.

## Lo que falta para decidir

La aceptación EVM de stake 0 y ventana 1 s demuestra precisamente por qué esta prueba
es insuficiente para afirmar admisión. **No se ejecutaron ValidationManager,
parser ERC-7562, depósito agregado, reputación ni mempool.** La fuente fijada de
referencia exige stake para ciertos accesos a almacenamiento y más de 30 s restantes;
son reglas leídas, no resultados ejecutados en este incremento.

Además, ValidationManager compara con `Date.now()` del host; los fixtures usan
19/sep/2026. Una futura prueba histórica del bundler debe declarar su reloj de
laboratorio; estos inputs vencidos no prueban aceptación actual. No cambiar reloj
de un servicio real ni desactivar caducidad para pasar. Una prueba con vigencia
actual requiere otro protocolo/fixture claramente registrado.

La instalación completa sigue incompleta por red y parada previa: la revisión
automática rechazó consultar el instalador después de detenerlo. No se retomó ni
se cambió de proveedor. No se realizó ninguna instalación en este incremento.
Faltan dependencias como ethers para ejecutar el bundler completo fijado.

**Queda un incremento del presupuesto acordado.** Su objetivo debe ser resolver
la admisión completa en un entorno permitido y establecer si existe una vía
documentada de financiación externa compatible con cero capital/garantías del
usuario. No afirmar financiación por tener un modelo de reparto o fondos ficticios.
No contactar, crear cuentas ni gastar sin autorización específica. Si esa evidencia
sigue bloqueada, recomendar congelar desarrollo activo conservando las condiciones
exactas para retomarlo; no ampliar inventarios para sustituir esa decisión.

Confianza alta en la corrección de la validación local y sus seis controles. La
financiación y rentabilidad permanecen no demostradas. Ninguna captura nueva de
oportunidades, ruta completa, AA incluido, Nitro/DA o ingreso fue realizada aquí.
