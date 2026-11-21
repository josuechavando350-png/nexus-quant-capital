# Representación de cantidades históricas de Census

Census conserva siete valores WAD como cadenas decimales, incluidos cuatro ceros. El consumidor prueba si una cantidad puede pasar por diferentes formatos de enteros sin truncarse ni cambiar de signo. Conserva el nombre y el valor de cada campo. Los valores mantienen su unidad original en todo el informe. El proceso opera sobre los bytes archivados en NQC.

| Proyecto | Operación comprobada | Resultado en las siete entradas |
|---|---|---|
| cosmos/cosmos-sdk | `ParseUint`, serialización JSON, deserialización y comparación mediante el paquete Go `cosmossdk.io/math` compilado desde el checkout | Siete round trips exactos |
| lfdt-ibc/ibc-go | La definición protobuf de `Token.amount` y el predicado de `Token.Validate` especifican una cadena de entero estrictamente positivo. El lector verifica ese predicado con Cosmos SDK | Tres cantidades satisfacen la restricción. Las cuatro de valor cero quedan fuera |
| CosmWasm/cosmwasm | El esquema JSON de respuesta de saldo del ejemplo de staking indica cadena. El esquema tipado enlazado desde el mismo contrato fija 128 bits sin signo | Las siete caben |
| MystenLabs/sui | Cruza el campo de almacenamiento `Balance.value` con su declaración `MoveStructLayout`. Comprueba si la magnitud se puede expresar con ese ancho | Los tres valores observados de 70, 77 y 82 bits exceden el campo de 64 bits |
| starkware-libs/cairo | La declaración Serde de `u256` define los campos `low` y `high` de 128 bits. La división en campos se contrasta con la reconstrucción independiente desde bytes | Siete reconstrucciones exactas. El control en 2¹²⁸ cruza de campo |

La integración con Cosmos SDK ejecuta el paquete real sin red. Las otras cuatro usan las declaraciones de las revisiones fijadas como referencias. Se comprobaron diez controles adicionales, incluidos los límites de 64, 128 y 256 bits, signo, exponente, cero inicial y el entero 2⁵³+1, que no se conserva al convertirlo a binary64. El producto sólo informa de la representación de las cantidades. No se generan paquetes de transferencia ni se ejecutan cadenas o contratos. El estado histórico de capacidad, captura y rentabilidad de NQC conserva su alcance.

## Reproducción offline

Se necesita el checkout de las cinco revisiones y la distribución oficial Go 1.27.4 para Linux amd64. La huella SHA-256 del archivo de distribución es `7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840`. Dos compilaciones offline, en directorios y cachés Go separados, produjeron el ejecutable con SHA-256 `606b9b741a14f37ae2164782f5cf5525d08d1e57efdf555f846123a104c92ede`. Se ejecutaron ambos con los mismos insumos y coincidieron los cinco recibos completos.

```sh
export NQC_EVM_LAYOUT_SOURCES="$PWD/upstream"
export NQC_STATE_GO=/ruta/go/bin/go
python3.12 -B -m superhunter.tools.prepare_state_amount_reader "$NQC_EVM_LAYOUT_SOURCES" "$NQC_STATE_GO" /tmp/nqc-amount-reader
export NQC_STATE_HELPER=/tmp/nqc-amount-reader
python3.12 -B -m unittest superhunter.tests.test_product_state_formats_batch
```

La preparación publica sólo una copia con la huella esperada y exige un destino nuevo. El consumidor comprueba las revisiones, los archivos y el ejecutable en cada sesión. Con el ejecutable preparado se reutiliza la compilación. Cada consulta vuelve a enviar las cantidades al proceso. [Código del consumidor](product_state_formats_batch.py) · [Datos, controles y recibos](product_supply/census-state-amounts-acceptance.json)
