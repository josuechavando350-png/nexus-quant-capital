# Representación de la hora del encabezado de Census

El bloque histórico 25 437 474 ya archivado por NQC declara la hora Unix 1 782 906 587. El consumidor comprueba si puede conservar ese entero al proyectarlo en cuatro interfaces. El número de bloque de Ethereum no determina un slot de Solana. El resultado deja desconocidos el slot, la época, el inicio de época y la época de planificación. Cada informe conserva por separado los campos presentes y los ausentes.

| Proyecto | Operación | Evidencia |
|---|---|---|
| LiteSVM/litesvm | Ejecuta el constructor y los getters del tipo nativo Clock de Linux x86-64 | Recupera la hora y rechaza un slot negativo, un slot mayor que u64 y una hora mayor que i64 |
| otter-sec/anchor | Ejecuta la clase numérica Borsh original y las funciones u64/i64 de esa revisión con las dos dependencias auténticas del lock | La hora se codifica como `dbfe446a00000000` y se decodifica sin pérdida |
| anza-xyz/mollusk | Entrega su declaración protobuf Clock a protoc para codificación y decodificación. Una segunda implementación comprueba campos, etiquetas y enteros del resultado | El único campo presente usa etiqueta 5 y bytes `28dbfd93d206` |
| anza-xyz/agave | Su vista UiClock especifica los nombres JSON y la correspondencia de campos que conserva el consumidor | La proyección textual conserva `unixTimestamp`. Cualquier campo omitido permanece desconocido |

Los enteros del informe se imprimen en decimal para poder conservar valores mayores que 2⁵³ en los clientes. La representación legible del informe no es una respuesta RPC. Una prueba usa el control numérico de cinco campos publicado por LiteSVM. Otra verifica la conservación de una hora negativa y un slot mayor que el rango exacto de binary64. Proto3 puede emitir los mismos bytes para cero conocido y ausente. El consumidor conserva la máscara de presencia junto a la carga. Se utilizaron únicamente clases de datos y códecs. No se instancian máquinas virtuales ni se inician cadenas.

## Verificación de publicaciones y repetición

Los [archivos de distribución](product_supply/clock-format-assets.json) están fijados por SHA-256. Las descargas de bn.js y buffer-layout también se contrastan con los SHA-512 del lock de Anchor. Sus archivos de licencia se revisaron como MIT. Los dos paquetes de LiteSVM declaran MIT; la distribución nativa Linux se vincula a la misma revisión mediante el [expediente de procedencia](product_supply/clock-format-provenance.json). El consumidor comprueba la firma DSSE, el certificado de flujo de publicación de GitHub, la cadena Fulcio a la hora registrada, el SHA-512 de ambos paquetes y el commit descrito por la declaración SLSA. La comprobación no incluye la prueba de inclusión de Rekor ni una recompilación propia del addon. El SHA-256 de protoc 32.1 coincide con el campo digest de la publicación oficial.

Para preparar el directorio local una vez desde la raíz del producto, seleccionar un directorio de trabajo nuevo y exportarlo como `NQC_SLOT_KIT`. El siguiente ejemplo descarga sólo los cinco paquetes registrados. Las posteriores ejecuciones son offline:

```sh
python3.12 -B - <<'PY'
import hashlib, json, os, pathlib, urllib.request
kit = pathlib.Path(os.environ["NQC_SLOT_KIT"])
kit.mkdir(exist_ok=True)
assets = json.loads(pathlib.Path("superhunter/product_supply/clock-format-assets.json").read_text())["assets"]
for name, row in assets.items():
    target = kit/name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == row["sha256"]:
        continue
    with urllib.request.urlopen(row["url"], timeout=90) as response:
        raw = response.read(16_000_000)
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError(f"hash inesperado para {name}")
    target.write_bytes(raw)
PY
export NQC_EVM_LAYOUT_SOURCES="$PWD/upstream"
python3.12 -B -m unittest superhunter.tests.test_product_slot_formats_batch
```

La ejecución requiere el Node del perfil de [formatos EVM](FIXED_EVM_LAYOUT.md), OpenSSL y espacios de nombres de usuario/red Linux. [Recibos por proyecto](product_supply/fixed-clock-acceptance.json)
