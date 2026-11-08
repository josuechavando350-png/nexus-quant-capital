# Cobertura de instrucciones y aristas condicionales OBSERVADAS

Esta unidad **no** busca vulnerabilidades en programas externos, no mide
exhaustividad, no hace RPC ni configura un nodo. Ejecuta únicamente los dos
controles aritméticos propios fijados que utiliza `evm_sequence_fuzz`.

## Diferencia respecto a la entrega anterior

`evm_feedback` deduce rasgos a partir de entradas, estados y resultados visibles.
`evm_opcode_trace` ejecuta el binario Geth fijado con `run --trace`, utilizando
los *mismos* contratos y la selección de secuencias de `evm_feedback`. Registra
PCs de instrucciones ejecutadas y aristas observadas de `JUMPI` —tomado o
continuación— para **cada** pareja contrato/configuración; su informe indica
exactamente cuáles de las secuencias disponibles se trazaron.

El trabajo de esta entrega está en **medir** cobertura; las mutaciones del
corpus precedente no fueron seleccionadas por nuevas aristas de código. No se
atribuye fuzzing guiado por código ni un hallazgo original a estas mediciones.

## Contrato de evidencia

1. Se exige la referencia externa al hash del código actual.
2. Antes de trazar, se reproduce **todo** el paquete previo `fuzz-owned-evm` con
   los binarios oficiales fijados y se recalcula su selección observable.
3. Se recompilan las fuentes locales, se vuelve a ejecutar el constructor para
   cada configuración y se rastrean todas las llamadas de las secuencias
   seleccionadas. El hash del stdout sin trazas, la raíz de estado, la entrada,
   los resultados de las llamadas y los estados persistentes deben coincidir con
   el paquete nativo completo. No se admite un `output.json` inventado.
4. Cada contador PC y opcode se vincula al **bytecode compilado** y a los inicios
   de instrucción, saltándose los inmediatos de PUSH1..PUSH32. Los saltos solo
   admiten destinos JUMPDEST; se registran las dos posibilidades observadas de
   JUMPI sin interpretar las rutas no ejecutadas.
   Cuando el destino de un JUMPI coincide con el PC de continuación y ese
   opcode es JUMPDEST, una traza sin pila NO permite discriminar salto tomado
   de continuación. Se registra `indeterminate` en lugar de inventar el sentido.
   Un JUMP incondicional al JUMPDEST inmediatamente siguiente también es legal.
5. `verify-opcode-traces` repite las compilaciones, el replay previo y las
   nuevas trazas; comprueba las fuentes y rechaza cambios en el resultado,
   informe, recibos o AuditLog aunque se recalculen los hashes del paquete.

## Uso local

```bash
python3 -m superhunter review-opcode-traces \
  --native-bundle /privado/fuzz-owned-evm \
  --solc /privado/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /privado/evm \
  --expected-source SHA256_DEL_SNAPSHOT_ACTUAL \
  --out /privado/opcodes-nuevo
python3 -m superhunter verify-opcode-traces \
  --bundle /privado/opcodes-nuevo \
  --native-bundle /privado/fuzz-owned-evm \
  --solc /privado/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /privado/evm --expected-source SHA256_DEL_SNAPSHOT_ACTUAL
```

Las carpetas son privadas, nuevas, externas al checkout; no se sobrescriben.
Los binarios no se incluyen en el ZIP de entrega. El ejecutable EVM debe
coincidir byte a byte con el hash fijado anteriormente; no se admiten flags,
fuentes, targets ni bytecodes arbitrarios desde CLI.

## Límites que NO se deben ocultar

- **Observado** no significa exhaustivo ni equivale a la totalidad de rutas
  posibles. El número de sitios PC decodificados incluye posibles metadatos o
  bytes de código nunca alcanzables: no se calcula un supuesto porcentaje de
  cobertura alcanzable a partir de ese denominador.
- La captura deshabilita stack, memoria y storage de las trazas para limitar
  datos y volumen. Se mantienen los volcados de estado y las comprobaciones
  nativas del paquete previo, no se ofrece un trazador de flujo de datos.
- Los perfiles utilizan el mismo compilador y el mismo motor EVM. Repetir una
  ejecución no aporta independencia de implementación.
- Una aserción revertida no representa beneficio, transferencia persistente ni
  vulnerabilidad original demostrada. Los controles tienen defectos conocidos.
- La verificación de la firma de Geth y el SHA de solc se tratan como requisitos
  previos; el hash de un paquete no demuestra quién lo creó ni que fuera
  producido en otra máquina.
- Los presupuestos, el formato Geth 1.17.10, y la profundidad uno impiden
  aplicar esta unidad como trazador EVM universal. Callframes externos, CALL
  anidados, bibliotecas vinculadas o redes reales están fuera del perfil.

No cambia el catálogo de 27 requisitos, 50 capacidades ni 25 iniciativas.
No habilita workflow legado, transacciones, firma o despliegue.
