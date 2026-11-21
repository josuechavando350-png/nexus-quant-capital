# Disposición del bytecode de los tres controles de NQC

El consumidor recupera los tres resultados de compilación que NQC conserva en `tests/fixtures/bytecode_native_capture.json`. Reconoce la sección CBOR de solc 0.8.30, separa sus 53 bytes y reconstruye la posición de cada instrucción y cada operando. El límite entre código y metadatos y la pertenencia de un dato inmediato importan al citar una instrucción en una revisión. Cada bloque informa de su requisito de pila de entrada y efecto neto. Los resultados señalan los bloques con mayor requisito, además de las características que dependen del fork.

| Proyecto | Participación | Comprobación |
|---|---|---|
| shazow/whatsabi | Ejecución TypeScript | Longitud de inmediatos, nombres, entradas mínimas y cambio neto de pila |
| bluealloy/revm | Ejecución Rust | El módulo de bytecode devuelve anchura y entradas/salidas de pila mediante su API real |
| argotorg/hevm | Referencia | Las etiquetas de cada posición coinciden con su tabla de mnemónicos |
| runtimeverification/evm-semantics | Referencia | Reglas de codificación y activación por fork procedentes de la especificación K |

Los dos módulos ejecutados procesan los bytes en procesos separados, sin red. Los archivos de los cuatro proyectos provienen de sus revisiones en Git y se cotejan por SHA-256. Sólo se usan el módulo de opcodes de cada biblioteca y las declaraciones citadas de las dos referencias. El reensamblado de los operandos de solc aporta una tercera implementación. Las posiciones encontradas describen el código almacenado. No se ejecutó ningún contrato ni se midió la alcanzabilidad de los bloques.

| Control propio | Bytes de código | Instrucciones | Bloques |
|---|---:|---:|---:|
| conservation | 768 | 510 | 58 |
| delayed_credit | 769 | 510 | 58 |
| unreachable | 715 | 472 | 56 |

Se verificaron los dos lectores con una instrucción truncada y con un inmediato que contiene el valor de JUMPDEST. KEVM deshabilita PUSH0 en Berlín. El expediente por proyecto conserva las rutas, revisiones, huellas de los insumos, bloques con mayor requisito y resultados. [Recibos](product_supply/fixed-opcodes-acceptance.json)

## Reproducción

Se requieren los cuatro checkouts completos en `NQC_EVM_LAYOUT_SOURCES`, un Linux con espacios de nombres de usuario/red y las distribuciones de Node y Rust del perfil. `node` 24.22.3 y `rustc` 1.98.1 deben estar en PATH. El compilador Rust usa el enlazador del sistema. Las huellas de ambos ejecutables están en el expediente. Cada llamada a `review` vuelve a procesar los casos y coteja el oráculo publicado.

La prueba independiente recompila las tres entradas con la distribución Linux x86-64 de solc 0.8.30. Verifica los objetos completos contra los históricos, obtiene el listado de instrucciones del compilador y reconstruye el oráculo. Su ejecución de aceptación se realizó dos veces durante este lote. No forma parte de cada consulta del producto. Para repetirla, indicar el ejecutable exacto en `NQC_EVM_LAYOUT_SOLC`; el lector valida SHA-256 antes de ejecutarlo.

```sh
python3.12 -B -m superhunter.tests.test_product_evm_standards_batch
python3.12 -B -m superhunter.tools.rebuild_fixed_opcode_oracle "$NQC_EVM_LAYOUT_SOLC" > /tmp/nqc-opcode-oracle.json
cmp /tmp/nqc-opcode-oracle.json superhunter/product_supply/fixed-opcodes-solc.json
```
