# Capacidades nativas de SUPERHUNTER

El registro actual contiene **16 grupos y 29 identidades**: 28 ejecutan código y una aporta reglas consumidas. Cada productor nuevo tiene controles propios reproducidos. El total conjunto con los dominios de Astra se acredita mediante una sola sesión y una matriz que conserva todas las operaciones sin duplicar identidades.

El checkpoint conjunto `37a0d5261ae52ece080d18b294042931112f2861` acredita **139/200 identidades** en 222 respuestas: 101 ejecutables, 38 referencias, 149 operaciones y diez identidades con operaciones múltiples. Los 17 dominios y 15 grupos nativos seleccionados terminaron sin bloqueos; el verificador rechazó 20 alteraciones. [Aceptación conjunta](product_supply/consolidated-acceptance-139.json) · [Matriz de 200](INTEGRATION_STATUS_200.md). La segunda ejecución del mismo commit fue aceptada y sus 222 respuestas coinciden byte por byte.

grpcurl se añade después de ese checkpoint. Tiene dos replays nativos y una sesión real de dos consultas mediante `query-product`, que acredita su operación y su identidad 69. Esto no se presenta como una ejecución conjunta de 140 identidades. [Recibo por el producto](product_supply/grpc-schema-native-product-session.json).

El checkpoint publicado `b87788962072578f9fb7ec5b584a06868639d89a` tiene una ejecución completa aceptada: **84/200 participaciones**, 72 de ejecución y 12 de referencia, con 221 respuestas, 200 fuentes directas y ocho alteraciones rechazadas. Usó los 12 grupos y 25 identidades del contrato histórico 84. La segunda ejecución desde otro checkout del mismo commit terminó con `OSError` antes de emitir el expediente completo; no se acredita reproducción byte por byte y la causa concreta permanece sin determinar. [Aceptación y fallo conservados](product_supply/native-acceptance-84.json) · [Transcripción de 84](product_supply/native-session-84.json).

Los tres grupos añadidos después de ese checkpoint —RLP, mutación y fuzzing Python— no se atribuyen a aquella ejecución. El [checkpoint anterior de 70](product_supply/native-acceptance-70.json) también permanece inmutable. Ninguno de estos controles acredita vulnerabilidades originales.

## Un solo producto

Los motores participan en `query-product`, usan las identidades originales del catálogo y publican recibos en el mismo `ProductIndex`. `native-capabilities` devuelve sus resultados; `integration-coverage` y `integration-matrix` calculan el estado a partir de esos recibos. Las fuentes, versiones, hashes, controles negativos y límites se conservan junto a cada resultado. Un productor que falla no publica acreditaciones parciales del grupo. Los grupos independientes pueden terminar; la CLI devuelve salida 2 si hay grupos bloqueados. Al repetir la selección se retiran sus recibos anteriores. El verificador completo exige cero bloqueos.

La selección de los grupos se configura en un único archivo JSON mediante `--native-kits`. Las claves admitidas están fijadas en código; el archivo sólo proporciona directorios locales, sin módulos ni comandos arbitrarios. Las rutas relativas se resuelven respecto al propio manifiesto. Una selección duplicada entre archivo y CLI se rechaza.

[Ejemplo de configuración](product_supply/native-kits-example.json).

## Incorporaciones

| Repositorio | Función comprobada |
|---|---|
| EVMole | Recupera selectores de los contratos históricos NQC y detecta un cambio controlado de interfaz. |
| WhatsABI | Contrasta los selectores con el compilador, sin RPC ni consulta de firmas. |
| Slither | Detecta `tx.origin` en el positivo OWNED; los dos controles negativos quedan sin ese diagnóstico. |
| crytic-compile | ABI, AST, bytecode de creación y runtime coinciden con solc directo. |
| Schemathesis | Acepta tres respuestas válidas y rechaza quince alteraciones del contrato OpenAPI propio. |
| Scapy | Interpreta tres paquetes propios y conserva la truncación y el checksum incorrecto del control alterado. |
| Recog | Dos reglas originales identifican banners locales de Apache/nginx; un banner desconocido no coincide. Participa como referencia, sin ejecutar el motor Ruby. |
| Cppcheck | Detecta nulidad y acceso fuera de rango en C; el control corregido queda limpio. |
| Capstone | Decodifica instrucciones y saltos, detecta el control desalineado y contrasta límites con objdump. |
| Betterleaks | Detecta dos patrones de credenciales falsas; deja limpios los controles benignos. |
| TruffleHog | Coincide en los dos patrones sintéticos, con verificación remota apagada. |
| mitmproxy | Interpreta doce controles de formato HTTP propios, incluidos mensajes válidos y longitudes o encabezados contradictorios. |
| xnLinkFinder | Extrae rutas y parámetros de respuestas JavaScript/gzip locales; conserva los controles vacíos y corruptos. |
| ffuf | Distingue rutas conocidas y respuestas comodín de un servidor propio en una red de loopback aislada. |
| Gobuster | Contrasta las rutas del mismo servidor y rechaza respuestas comodín ambiguas. |
| Arjun | Comprueba un parámetro fijo del servidor propio, sin aceptar una URL externa. |
| Echidna | Genera y reproduce una secuencia que refuta un invariante de contabilidad propio y pasa sobre el contrato reparado. |
| Medusa | Aporta una segunda secuencia, reproducida independientemente; se fija el corpus, sin afirmar una semilla que el motor no ofrece. |
| SpotBugs | Analiza clases Java propias y reconoce el control de nulidad; la clase corregida queda sin diagnósticos. |
| FindSecBugs | Añade el diagnóstico SQL_INJECTION_JDBC al mismo análisis Java; un test en memoria contrasta la separación de consulta y parámetros. |
| crytic/properties | Ejecuta tres propiedades ERC20 originales sobre balances propios defectuosos y reparados. |
| Immunefi forge-poc-templates | Ejecuta contratos de simulación originales para transferencias con comisión y retornos falsos, sin crédito contable indebido. |
| Policy Sentry | Clasifica cinco políticas IAM propias; conserva acciones desconocidas como inconclusas y no evalúa permisos efectivos de una cuenta. |
| Hardhat | Compila seis contratos propios y contrasta ABI, AST, bytecode y almacenamiento con solc directo. |
| OpenZeppelin Upgrades | Acepta una ampliación compatible del almacenamiento y rechaza reducción de tipo, reordenamiento, eliminación y renombramiento no autorizado. |
| OpenZeppelin Ethernaut | Ejecuta sus bibliotecas RLP sin cambios para leer el encabezado histórico de Census y controles de longitud, listas y truncación; una comprobación separada rechaza las codificaciones no canónicas que el lector admite. |
| Mewt | Produce cuatro mutaciones aritméticas propias; las pruebas fuertes matan cuatro y una prueba débil deja sobrevivir la multiplicación. Ocho repeticiones por compilación directa corroboran el resultado. |
| Atheris | El fuzzer nativo encuentra un desbordamiento contable introducido en un parser propio, guarda el corpus, reproduce el fallo y comprueba la reparación durante 512 callbacks. |
| grpcurl | Lee servicios, métodos y tipos de dos esquemas propios, detecta cambios de streaming y de codificación, y contrasta sus descriptores con un decodificador independiente; no abre un servidor ni invoca RPC. |

Las inferencias de argumentos/mutabilidad que EVMole no resuelve se conservan como incertidumbre. Los releases binarios y las revisiones del catálogo se distinguen; no se afirma que todo binario haya sido reconstruido desde el commit del catálogo. En Hardhat, 299 de 300 fuentes TypeScript comparadas coinciden con el catálogo; la diferencia del campo `test` frente a `tests` queda registrada. Las 132 fuentes comparadas de OpenZeppelin coinciden. La repetición en un mismo host demuestra reproducibilidad de estos controles, sin autenticar al productor ni establecer precisión general.

Las 29 identidades conservan sus ámbitos específicos. Una prueba de formato HTTP no acredita toda la capacidad de proxy, un control de almacenamiento no certifica la seguridad completa de una actualización y una clasificación IAM no sustituye la evaluación de autorización efectiva. Si otro grupo ya usa el mismo repositorio, sus operaciones se conservan pero la identidad se cuenta una sola vez en la consolidación.

## Reproducir

Preparar el perfil de la [sesión publicada por Astra](SOURCE_ASSURANCE.md) y los kits descritos en los archivos `*-native-build.json`, `*-native-evidence.json` y sus manifiestos fijados. El checkpoint conserva los pines exactos usados; la preparación portable de todos los kits sigue ampliándose en esta rama.

El kit Java se reconstruye desde el paquete oficial Debian de OpenJDK 21.0.13 y 25 JAR de Maven, con 202 archivos verificados. La receta fijada `java-native-rebuild.txt` conserva los bytes de la JVM y del compilador, y excluye el almacén de certificados generado por el host. Las detecciones y los cuatro bytecodes propios permanecen idénticos. El kit EVM también utiliza ahora la distribución oficial fijada de Node; la sesión histórica de 70 conserva su contrato anterior.

Al comando de la sesión completa añadir:

```sh
--native-kits "$KITS_JSON" --review-queries
```

Con `--gosec-kit` y `--embedded-root-manifests`, el ejecutor incluye las dos consultas del PR 117 y la consulta de capacidades nativas. Cada invocación consume los kits comprobados, vuelve a ejecutar los controles seleccionados y coteja sus bytes normalizados antes de acreditar una identidad.

Para comprobar los expedientes archivados, sin afirmar nuevas ejecuciones de motores:

```sh
python3.12 -B -m superhunter.tools.verify_native_session --archive --contract-version 70 --check-controls superhunter/product_supply/native-session-70.json
python3.12 -B -m superhunter.tools.verify_native_session --archive --contract-version 84 --check-controls superhunter/product_supply/native-session-84.json
python3.12 -B -m superhunter.tools.verify_native_session --archive --contract-version 139 --check-controls superhunter/product_supply/native-session-139.json
```

[Registro de la ejecución](product_supply/native-acceptance-70.json) · [Transcripción completa comprimida](product_supply/native-session-70.json) · [Matriz de las 200 identidades](INTEGRATION_STATUS_200.md) · [Fuentes y alcance de Git](SOURCE_CHECKOUT.md).

La sesión de 70 se ejecutó con cambios locales y conserva esa limitación. La sesión de 84 procede de un checkout limpio del commit publicado b877889. Los kits y el host de las repeticiones son compartidos; no se afirma independencia de hardware. Las fuentes históricas de NQC se preservaron: 642 archivos comprobados, cero workflows activados.

RLP conserva los archivos Git y avisos originales; el control no ejecuta el juego completo de Ethernaut. Mewt está reconstruido desde el commit catalogado, con sus 288 archivos de dependencias cotejados y aviso AGPL conservado. Atheris utiliza el wheel oficial 3.1.0; no se presenta como un binario reconstruido desde el commit catalogado. El corpus real descubierto se conserva también como bytes hexadecimales y SHA-256 en los JSON publicados. Los errores son deliberados y locales; no se cuentan como hallazgos de terceros.
