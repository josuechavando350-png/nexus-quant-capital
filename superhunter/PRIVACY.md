# Revisión privada de logs y reportes — entrega local

Estado: implementado y probado en la copia local; no publicado en GitHub.
Base de integración: `8af99b087de075ff18245c035192dbf39ccbde2e`, rama
`feat/superhunter-contract-bridge-20261103` del repositorio NQC.

## Cambio probado

El CLI anterior incluía `str(exc)` en su respuesta. Se reprodujo una fuga con
un marcador sintético en el nombre de un campo JSON inválido. El nuevo CLI
emite un código fijo y no repite ese contenido. Los errores de argumentos
públicos tampoco repiten opciones, valores o rutas proporcionados por el usuario.
No se afirma una vulnerabilidad de un protocolo externo ni una severidad bounty.

## Recorrido integrado

`privacy.py` se utiliza en el renderizador Markdown, la salida JSON de revisión,
los diagnósticos y el log del worker de pruebas. Figura como componente con
pruebas obligatorias y dependencias en el control conjunto de calidad.

- Las verificaciones del puente se realizan contra los artefactos originales.
- Solo después se crea una copia redactada de la decisión para revisión.
- `decision.json` incluye metadatos `privacy` y conserva `REVIEW_REQUIRED`.
- `review.md` se identifica como derivado; no es una copia literal de la evidencia.
- Los originales, sus hashes, las fuentes nativas y el grafo causal no se cambian.
- Los archivos de intercambio como `request.json` y los originales siguen
  pudiendo contener información sensible: no deben publicarse.
- El log de QA se filtra antes de persistirlo. Los resultados, fallos y contadores
  no se alteran: redactar un error no convierte una prueba fallida en aprobada.

## Uso del nuevo comando

Desde la raíz de la copia de NQC, con las dependencias ya instaladas:

```bash
python3 -m superhunter redact-log /ruta/privada/entrada.log \
  --out /ruta/privada/revision-nueva
python3 -m superhunter check --out /tmp/superhunter-qa-nuevo
python3 -m superhunter verify-check --bundle /tmp/superhunter-qa-nuevo
python3 -m unittest discover -s superhunter/tests -v
```

`redact-log` acepta un único archivo local UTF-8, de hasta 2 MB. No modifica
su entrada. Escribe `redacted.txt`, `redaction.json` y un manifiesto final en
una carpeta nueva 0700; los archivos son 0600. Rechaza symlinks de entrada,
archivos no regulares y sobrescritura de salidas. Un resultado 0 significa
que se creó el derivado, **no** que el contenido sea seguro para publicación.

Las reglas cubren campos sensibles etiquetados, cabeceras de autorización,
cookies, userinfo en URLs, cadenas con formato JWT y bloques de claves privadas,
incluidos bloques truncados. Las notas con frases de recuperación etiquetadas
se ocultan. Las direcciones públicas de tokens en la estructura económica se
conservan. No se comprueba si una credencial es válida ni se intenta utilizarla.

## Límites explícitos

Es una detección por reglas finitas, no un monitor semántico completo. Puede
omitir secretos no etiquetados, ofuscados, codificados o en imágenes; también
puede ocultar valores no secretos. No hay captura de pantallas, vigilancia,
consultas externas ni almacenamiento de credenciales detectadas.

El texto redactado puede perder sintaxis de un log originalmente JSON: se
exporta como texto para lectura humana, no como sustituto del documento fuente.
Para estructuras del propio puente se usa una transformación estructurada que
conserva JSON válido y rechaza colisiones de claves. El resumen solo incluye
categorías y contadores; no conserva fragmentos ni hashes individuales de secretos.

`manual_review_required` siempre es true y `all_secrets_detected` siempre false.
El punto 29 del catálogo queda **PARCIAL**, no completo. Los puntos 45, 47 y 48
conservan su alcance parcial. Ninguna de las 50 capacidades se certifica completa.

## Validación realizada

Baseline actual: 173 pruebas, no 157; el head ya incluía 16 pruebas del grafo
causal posteriores al registro anterior. Se verificaron contra Git los bytes
runtime/tests y entradas de política materializados. La suite ampliada ejecutó
209 pruebas (36 nuevas), sin fallos, errores ni omisiones. Se ejecutó además
el control conjunto y su verificador en procesos separados.

Las pruebas de privacidad usan marcadores sintéticos, no secretos reales.
Incluyen el diagnóstico antes/después, preservación de evidencia, fallos de
pruebas que siguen siendo fallos, redacción idempotente, formatos incompletos,
límites de tamaño, permisos, rechazo de symlinks y el registro de los 50 puntos.

No se ejecutó Forge, forks, RPC, operaciones blockchain, la suite histórica
completa de NQC ni su verificador de aislamiento. No se realizó publicación,
fusión, workflow ni cambio remoto. La entrega incluye un parche aplicable a
la base indicada; la disponibilidad de lectura GitHub no implica escritura.
