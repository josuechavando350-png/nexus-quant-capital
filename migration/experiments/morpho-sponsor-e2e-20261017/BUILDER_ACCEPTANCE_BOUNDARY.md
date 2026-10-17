# Límite entre EVM y financiación comercial

La EVM local acredita flujos, gas cobrado y reversiones de fixtures. No acredita la identidad de un builder real, sus fondos disponibles, promesa de financiar CREATE, admisión, inclusión, condiciones de recuperación ni ausencia de deuda personal. Todos esos flags externos permanecen `null`. El actor `simulated_builder` es una dirección de laboratorio y no se atribuye a Titan ni Quasar.

Se revisa offline el expediente fijado en `544fd2d...`, `migration/zero-capital-viability-20261017/SPONSORSHIP_REALITY_AUDIT.md`, y la revisión independiente `5e4d581.../SPONSOR_NO_RECOURSE_AUDIT.md`. Las páginas públicas citadas por esos expedientes son [Titan eth_sendBundle](https://docs.titanbuilder.xyz/api/eth_sendbundle) y [Quasar eth_sendBundle](https://docs.quasar.win/api/eth_sendbundle). No se consultaron relays ni se enviaron peticiones a esos servicios durante este estudio. Por tanto, se conserva la fecha y alcance documental anterior, sin afirmar una política nueva comprobada en producción.

| Aspecto | Titan según expediente | Quasar según expediente | Evidencia NQC |
|---|---|---|---|
| Adelanto condicional | Gas y value, sujeto a aumento de balance del builder | Gas, sujeto a aumento de balance del builder | Mecánica sintética, contraparte real UNKNOWN |
| Deploy + ejecución desde EOA vacía | No deducir aceptación de este contenido concreto | No extender gas documentado a cualquier CREATE/value | Despliegues locales pagados con anticipo; aceptación UNKNOWN |
| Aumento de ingresos | Debe atribuirse al builder | Debe atribuirse al builder | Coinbase pertenece a otro actor; solo fee separado del laboratorio |
| Fallo/no inclusión | Opciones de reversión/eliminación/reemplazo no prueban garantía | Tampoco garantizan inclusión o absorción de pérdidas | F01–F12 muestran exposiciones; recurso real UNKNOWN |
| `refundPercent` | Flujo de recompensa hacia usuario/beneficiario según condiciones | Flujo de refund documentado | No confundir con sponsorRefund del ejecutor, de dirección económica opuesta |

Un programa público verificable podría demostrar las condiciones aplicables; **no se exige por definición un contrato bilateral negociado**. Lo que falta es evidencia de cobertura, fondos, beneficiarios y ausencia de recurso aplicable al candidato, cualquiera que sea su instrumento legítimo. No se atribuye imposibilidad al hecho de no tener esa prueba.

## Puente de trazas

`reconcile.py` produce `evidence/gate-bridge.json` con las claves exactas del esquema anterior. Los importes, cap, nonce, direcciones y prestate hash se derivan de recibos locales. Conserva `chain_id=31337`; provider, avance **del builder real**, ingresos del builder real y todos los flags que implican evidencia externa quedan `null`. El financiador local y el builder local son distintos: la transferencia de uno no se rebautiza como anticipo del otro.

`bundle_gate.check` rechaza el input porque solo admite Ethereum mainnet. No se cambió chain_id a 1 ni un UNKNOWN a true para conseguir aprobación. Los campos U efectivamente devuelto, gasto efectivo y coste de oportunidad se guardan en el ledger contiguo; el esquema anterior no los expresa. Esto es un límite del esquema, no un FAIL financiero del protocolo.

Se comprobaron: adapter incluido en gas; cap distinto de gasto; U con recibo; avance no descontado dos veces; top-up separado cobrado; refund del usuario distinto del refund al sponsor; tip y priority fees no atribuidos al builder; fuentes/cadenas separadas; inventario donado excluido. Los márgenes positivos locales no activan admisión comercial.

## Puertas de Directiva 003

| Puerta | Estado local | Estado comercial |
|---|---|---|
| G0: propietario sin aportación/pasivo | Cero activos iniciales probado; no se crea deuda NQC en Morpho | PENDIENTE: condiciones de recurso externas UNKNOWN |
| G1: ejecución auténtica | PROBADO_EN_LABORATORIO con fuentes originales y estado sintético | PENDIENTE de testigo histórico |
| G2: financiación externa | SIMULADO con balance ajeno y devolución real local | PENDIENTE |
| G3: margen integral | PROBADO_EN_LABORATORIO a gas base; REFUTADO_BAJO_SUPUESTOS para sponsor a gas alto | PENDIENTE de todos los costes reales |
| G4: temporalidad/captura | NO_EJECUTADO | PENDIENTE |
| G5: recurrencia | Censo API verificado internamente | PENDIENTE de muestra económica y competencia |

Equivalencia con auditoría 001: allí G3 era temporalidad y G4 rentabilidad; aquí G3 es rentabilidad y G4 temporalidad. No se transfieren PASS por reutilizar un número.
