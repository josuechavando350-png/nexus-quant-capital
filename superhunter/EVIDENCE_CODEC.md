# Transporte de evidencia mediante tokens

El dominio `evidence-codec` comprueba si un consumidor local puede reconstruir las identidades y los hashes de evidencia de una sesión NQC después de su codificación en tokens. Su entrada fija contiene el propósito aprobado de cada proyecto y los campos de identidad, commit, papel y recibo de la matriz publicada en el PR 117. El consumidor vuelve a construir el índice histórico que enlaza 59 repositorios con sus pruebas. Esos 59 pertenecen al expediente de entrada.

| Componente | Participación observada |
|---|---|
| ggml-org/llama.cpp | Se ejecuta la función original `bytes_to_unicode` del convertidor de vocabularios sobre el alfabeto completo. Su tabla codifica los 48 457 bytes de los 200 expedientes, incluidos sus caracteres no ASCII. |
| sgl-project/sglang | La tabla de vocabulario y la declaración de tokens especiales de `tiny_tokenizer.json` se consumen como datos. Asignan los ID a las etiquetas del codificador. El consumidor coteja los 256 ID de byte y reserva el marcador de fin de texto. |
| vllm-project/vllm | Se compila y ejecuta el módulo Rust original de decodificación de tokens ByteLevel en un espacio de red aislado. El consumidor coteja SHA-256 y JSON y reconstruye el índice de pruebas. |

El perfil sólo cubre el vocabulario de prueba sin fusiones y los expedientes fijados. Los servicios de inferencia, los pesos y el razonamiento de modelos quedan sin evaluar. Un registro truncado, una identidad sustituida, un hash de prueba alterado y una secuencia UTF-8 incompleta deben quedar excluidos. El consumidor también rechaza identificadores de token reservados, negativos y de tipo distinto de entero.

La matriz de entrada es la respuesta 214 de las 220 de la [sesión histórica](product_supply/review-117-session.json). El [adaptador](product_evidence_codec.py) fija su hash, las tres revisiones Git y el SHA-256 de cada archivo utilizado. La función Python se extrae sin modificaciones del blob verificado; el archivo de origen atribuye la función a Transformers con licencia Apache-2.0. La compilación de este perfil utilizó `rustc 1.98.1` para Linux x86_64. El dominio comprueba el digest de su ejecutable. El enlazador y la biblioteca estándar forman parte del entorno local.

Para repetir las [pruebas](tests/test_product_evidence_codec.py) con los checkouts y el compilador ya preparados:

```sh
NQC_CODEC_TEST_SOURCES="$CHECKOUT/upstream" python3.12 -B -m unittest -v superhunter.tests.test_product_evidence_codec
```
