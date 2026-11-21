# Capacidades nativas de SUPERHUNTER

El checkpoint reúne las 59 participaciones de los PR 115/117 y once incorporaciones nuevas. Una ejecución sin red produjo 221 respuestas: **70 participaciones, 58 de ejecución y 12 de referencias consumidas**. Hay 200 checkouts directos verificados y 130 identidades pendientes de participación. El verificador independiente rechazó ocho alteraciones del expediente. Los controles no acreditan descubrimiento de vulnerabilidades originales.

## Un solo producto

Los motores participan en `query-product`, usan las identidades originales del catálogo y publican recibos en el mismo `ProductIndex`. `native-capabilities` devuelve sus resultados; `integration-coverage` y `integration-matrix` calculan el estado a partir de esos recibos. Las fuentes, versiones, hashes, controles negativos y límites se conservan junto a cada resultado. Un productor que falla no publica acreditaciones parciales del grupo.

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

Las inferencias de argumentos/mutabilidad que EVMole no resuelve se conservan como incertidumbre. Los releases binarios y las revisiones del catálogo se distinguen; no se afirma que todo binario haya sido reconstruido desde el commit del catálogo. La repetición en un mismo host demuestra reproducibilidad de estos controles, sin autenticar al productor ni establecer precisión general.

## Reproducir

Preparar el perfil de la [sesión publicada por Astra](SOURCE_ASSURANCE.md) y los kits descritos en los archivos `*-native-build.json`, `*-native-evidence.json` y sus manifiestos fijados. El checkpoint conserva los pines exactos usados; la preparación portable de todos los kits sigue ampliándose en esta rama.

Al comando de la sesión completa añadir:

```sh
--native-kits "$KITS_JSON" --review-queries
```

Con `--gosec-kit` y `--embedded-root-manifests`, el ejecutor incluye las dos consultas del PR 117 y la consulta de capacidades nativas. Cada invocación consume los kits comprobados, vuelve a ejecutar los controles seleccionados y coteja sus bytes normalizados antes de acreditar una identidad.

Para comprobar el expediente archivado, sin afirmar una nueva ejecución de motores:

```sh
python3.12 -B -m superhunter.tools.verify_native_session   --archive --check-controls superhunter/product_supply/native-session-70.json
```

[Registro de la ejecución](product_supply/native-acceptance-70.json) · [Transcripción completa comprimida](product_supply/native-session-70.json) · [Matriz de las 200 identidades](INTEGRATION_STATUS_200.md) · [Fuentes y alcance de Git](SOURCE_CHECKOUT.md).

La sesión de este checkpoint se ejecutó sobre una rama de trabajo con cambios locales. El recibo lo declara y deja pendiente la reproducción desde el commit publicado. Las fuentes históricas de NQC se preservaron: 642 archivos comprobados, cero workflows activados.
