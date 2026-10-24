# Recompilación del runtime histórico de Aave

Esta entrega vincula las observaciones históricas de Ethereum con dos
compilaciones locales. La del pool utiliza 42 fuentes recuperadas de Sourcify
v2 y EVM Cancun; FlashLoanLogic utiliza sus 28 fuentes de la página verificada
de Ethereum en Etherscan y EVM Shanghai. Ambas usan solc
`0.8.27+commit.40a35a09`, optimizador de 200 ejecuciones y `viaIR=false`.
Se conservan fuentes y parámetros originales; solo se cambia la selección de
salidas del compilador.

El compilador se descargó del espejo oficial `ethereum/solc-bin` después de
un HTTP 403 del servidor de binarios. Su SHA-256 se comprobó contra el índice
oficial retenido y quedó fijado en el verificador:
`b9977d500c17cba6f0032ca939ef98c4decf6363f19f386d05fb02f708115264`.
El binario descargable de 15.753.912 bytes no se incorpora al repositorio.

## Archivos y reproducción

- `source.json.gz`: respuesta completa original de Sourcify, sin modificar;
  incluye las fuentes, licencias, metadatos, parámetros y artefactos remotos.
- `compiler-list.json.gz` y `retrieval.json`: procedencia, hashes y fecha UTC
  de los archivos descargados. Gzip conserva el cuerpo original al descomprimir.
- `flashloan-etherscan.html.gz` y `flashloan-retrieval.json`: página y procedencia
  de las fuentes de FlashLoanLogic. El parser decodifica únicamente un literal
  de texto y `settings.json`; no ejecuta JavaScript de la página.
- `public/`: 90 solicitudes y respuestas de solo lectura, seis contratos en
  tres bloques, con acuerdo de dos proveedores, finalización y comprobaciones
  de canonicalidad anteriores y posteriores. Se conservan los bytes completos
  de código y proyecciones de encabezados; no son pruebas criptográficas de estado.
- `local/`: entrada, salida y stderr de la recompilación local y su auditoría.
- `preflight-001/`: compilación inicial y fallo real conservado. El FlashLoanLogic
  generado con el perfil del pool tiene 8.206 bytes; el desplegado tiene 8.227.
  El segundo perfil reproduce los 8.227 bytes sin descartar diferencias.
- `rule-excerpts.json` y los tres `.txt`: funciones completas extraídas de las
  fuentes compiladas, con archivo, líneas y hash de procedencia.
- `tests.txt`, `python-research-tests.txt`, `isolation.json` y `verification.json`:
  14 pruebas específicas y 256 pruebas Python generales aprobadas (las 14 están
  incluidas en las 256), control de aislamiento y hashes de entrega.

Desde `migration/nqc-miner`, con el compilador de hash indicado:

```sh
python research/aave_runtime_identity.py --compiler /ruta/solc-0.8.27 --output /ruta/auditoria-nueva
python -m unittest discover -s research -p test_aave_runtime_identity.py -v
```

La auditoría no usa red. Recompila fuentes literales en un directorio temporal
vacío con `--no-import-callback`, reproduce las solicitudes retenidas y compara 36 pares de código
(seis contratos × tres bloques × dos proveedores). La captura pública es un
paso separado; no se vuelve a ejecutar al auditar.

## Alcance de la comparación

El pool corresponde al `POOL_REVISION = 11` de la fuente recompilada. Sus cinco
bibliotecas son PoolLogic, BorrowLogic, SupplyLogic, FlashLoanLogic y
LiquidationLogic. También se resuelve el enlace de FlashLoanLogic a BorrowLogic.
La biblioteca reutilizada no se da por verificada por compilar junto al pool:
la prueba de regresión reproduce el desacuerdo real y exige su propio perfil.
Cada byte de runtime, incluidos los metadatos, participa en la comparación.
Solo se sustituyen las ubicaciones de enlaces e inmutables declaradas por el
compilador y la dirección propia del prefijo de biblioteca Solidity.

Los dos inmutables se identifican mediante el AST producido localmente:
`ADDRESSES_PROVIDER = 0x2f39d218133afab8f2b819b1066c7e434ad94e9e` y
`RESERVE_INTEREST_RATE_STRATEGY = 0x9ec6f08190dea04a54f8afc53db96134e5e3fdfb`.
Sus posiciones, valores y todos los enlaces constan en `local/audit.json`.

La compilación usa `bytecodeHash=none`: se demuestra equivalencia del runtime
de estas fuentes, no que su texto, comentarios o ruta Git sean el original
único. El estado histórico procede del acuerdo RPC retenido; no de pruebas de
estado. No se asigna una etiqueta semántica de lanzamiento por el número de
revisión, ni se extrapolan tres bloques al intervalo completo.

La equivalencia de estas seis piezas no certifica las dependencias externas
(oráculo, tokens, estrategia de tipos, configuración y liquidez), el estado
inmediatamente anterior a una transacción o su rentabilidad. La elegibilidad
ejecutable y todas las salidas de fase siguen abiertas. **43/100** global.
