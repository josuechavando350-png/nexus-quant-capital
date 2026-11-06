# SUPERHUNTER — verificación de traza EVM mediante intérprete independiente acotado

**Funcionalidad real, estrictamente offline:** el módulo `evm_bounded_replay.py` valida el expediente privado creado por `review-evm-forensic`, copia sus originales con manifiesto verificable y calcula por segunda implementación la secuencia completa de PCs, los valores de stack utilizados en saltos, PUSH/DUP/SWAP, comparaciones y operaciones aritméticas acotadas. El analizador anterior solo comprobaba continuidad de PCs, JUMPDEST y formato de traza; no podía distinguir que un `JUMPI` "taken" fuera falso por condición cero. Esta implementación sí lo refuta.

## Comandos

```bash
python3 -m superhunter replay-evm-forensic --bundle /privado/evm-forensic-verificado --out /privado/replay-nuevo
python3 -m superhunter verify-evm-replay --bundle /privado/replay-nuevo --expected-complete-sha256 SHA256_EXTERNO_PREVIAMENTE_GUARDADO
```

El segundo comando es un *replay independiente* que reconstruye primero los resultados anteriores desde los bytes originales y recalcula después todos los PCs y operaciones mediante un evaluador distinto. El reporte preserva `trace.jsonl`, `context.json`, `journal.jsonl`, `metadata.json`, `finding.json`, `receipt.json`, `REVIEW.md`, el manifiesto de la entrega anterior como `parent-complete.json`, `semantic.json`, `replay-receipt.json` y `REPLAY.md`. Todos son **privados** y no deben publicarse en GitHub.

## Alcance semántico

- EVM de stack, control de flujo y semántica de 256 bits: STOP; PUSH0..PUSH32; POP; DUP1..DUP16; SWAP1..SWAP16; ADD, MUL, SUB, LT, GT, EQ, ISZERO, AND, OR, XOR, NOT, SHL, SHR; JUMP, JUMPI y JUMPDEST.
- Hasta 4,096 pasos, 1,024 elementos de pila, 32,000 bytes de bytecode, no más de 2 MB de traza. Falla si faltan pasos, stack, condiciones o destinos correctos, si faltó STOP o si el opcode queda fuera del subconjunto.
- **No soporta** memoria, storage, gas semántico, llamadas externas, entorno de bloque, retorno, revert, precompilados, contratos arbitrarios ni estado de cadena. Ante estas características *rechaza* la capacidad de replay, no infiere PASS.
- La operación utiliza los datos de un emisor local que podría fabricar la traza y el journal. `BOUNDED_STACK_PC_REPLAY_MATCH` **no prueba Geth auténtico**, un incidente, un momento de ejecución, una vulnerabilidad, validez de código en producción ni equivalencia EVM completa. La identidad del productor y los hashes externos necesitan un custodio independiente.
- No hay RPC, escaneo, broadcast, secreto, fondos ni uso de programas de terceros.

## Criterios de aceptación

Rechazar una traza formalmente coherente con bytes y PCs, pero físicamente incompatible con el stack de la VM; aceptar el mismo control cuando es realizable dentro del subconjunto; comprobar que otro proceso reconstruye los originales y rechaza alteraciones aunque se recalculen hashes y manifiestos; preservar todas las pruebas antiguas en el QA general. El contador global de pruebas no prueba detección de vulnerabilidades reales.
