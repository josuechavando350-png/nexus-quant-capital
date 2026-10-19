# NQC038 — acceso a pruebas históricas

Estado al 19 de octubre de 2026: **acceso pendiente; cero pruebas nuevas del estado histórico**.
La alternativa concreta preparada es la prueba gratuita de Triport. No se creó
una cuenta, se obtuvo una clave ni se consumió su servicio. NQC036 y NQC037
permanecen intactos; el motor R5 no cambia.

## Qué cambió

1. Triport publica un rango histórico medido que incluye nuestro bloque padre
   66,744,161 y el ancla 66,753,418. Incluye `eth_getProof` entre los métodos
   sujetos a esa profundidad, pero advierte que las mediciones no garantizan
   disponibilidad en todos los canales. Esto permite elegir una prueba concreta;
   todavía no demuestra que el servicio entregue nuestro estado.
2. La documentación actual exige una clave para todas las rutas Robinhood,
   incluida `/public`. Los resultados antiguos del buscador que anuncian acceso
   sin clave no son una autorización vigente. La prueba anunciada dura siete
   días, usa una región europea y no requiere tarjeta para comenzar.
3. El adaptador `triport_intake.py` usa números de bloque fijos, documentados por
   el proveedor. Conserva íntegro el verificador NQC037: cabeceras por hash,
   raíz padre fijada, pruebas de cuenta/almacenamiento y hashes de código.
   No presupone que Triport acepte el objeto de bloque EIP-1898.
4. Revisar el código fijado de PathDB detectó una distinción operativa relevante:
   su lector histórico puede recuperar valores, mientras que `NodeReader`
   exige que la raíz exista en las capas actuales. `GetProof` necesita ese árbol
   para construir la prueba. Un snapshot etiquetado como archivo no garantiza
   pruebas antiguas mediante una consulta directa.

## Acceso propuesto, listo para revisión

Proveedor: [Triport](https://triport.io/docs/robinhood/public). Plan anunciado:
Free, siete días, sin tarjeta al inicio. Alcance solicitado: activar ese acceso y
ejecutar **hasta ocho lecturas**, secuencialmente, a un único endpoint. No se
incluyen planes de pago, renovación, contacto con terceros ni operaciones de cadena.

| Orden | Consulta | Posición y validación |
|---|---|---|
| 1 | `eth_chainId` | Debe ser 4663 |
| 2 | `eth_getBlockByHash` | Padre; reconstrucción del hash y raíz fijada |
| 3 | `eth_getProof` | PairOracle: 11 slots al cierre del padre |
| 4 | `eth_getCode` | PairOracle: hash contra la cuenta probada |
| 5 | `eth_getProof` | Cinco campos de control ArbOS en el padre |
| 6 | `eth_getBlockByHash` | Ancla observada; hash y send root |
| 7 | `eth_getProof` | Dos slots de historia en el ancla |
| 8 | `eth_getCode` | Runtime exacto del contrato de historia |

El primer resultado que desbloquearía la investigación sería la consulta 3,
aceptada por el verificador contra la raíz padre
`0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a`.
Si un método falla, se detiene la secuencia. No se sustituye el bloque por uno
más reciente para producir un aparente éxito.

`TRIPORT_PLAN.json` contiene las solicitudes completas, sin credenciales.
`REQUESTS.json` en una adquisición representa las operaciones lógicas NQC037;
`WIRE_REQUESTS.json` registra las solicitudes numéricas realmente usadas.
El selector numérico no lleva `requireCanonical`: la pertenencia a la raíz
se comprueba criptográficamente, pero la canonicidad independiente sigue pendiente.

La clave autorizada debe configurarse fuera de los archivos y del historial de
comandos como `NQC_TRIPORT_API_KEY`. No se imprime ni persiste. Una vez disponible:

```sh
python migration/experiments/nqc-038-archive-access/triport_intake.py collect --out /tmp/nqc038-acquisition
```

La carpeta de salida debe ser nueva. Se limita cada respuesta a 16 MiB y cada
petición a 30 segundos. No hay redirecciones, reintentos ni cambio de endpoint.
Los errores de proveedor se conservan por código, sin su cuerpo ni credenciales.
Una respuesta exitosa pero inválida se conserva para revisión; `FAILURE.json`
indica su rechazo. Los ocho resultados aceptados pueden revalidarse sin red con
el comando `verify` de NQC037.

## Qué ocurrió en la red

La consulta única `eth_chainId` al ejemplo de Dwellir que mostraba el buscador
devolvió HTTP 429. La página actual exige una clave propia, por lo que ese ejemplo
no queda establecido como acceso público. Se eliminó el identificador del registro
publicable y no hubo otro intento. No se recibió estado.

La lectura HTTP del explorador de snapshots devolvió 403. La lectura independiente
del puntero público de archivo en el host de snapshots también devolvió 403.
No se descargó una base de datos ni se probaron transportes alternativos tras
esos rechazos. Estos códigos no permiten atribuir por sí solos el bloqueo al
proveedor o a la infraestructura de ejecución.

Las rutas oficiales, PublicNode y BlockReq ya ensayadas en NQC036/037 no se
repitieron. No se reinició ni amplió la cuota agotada de Blockscout. No hay claves
configuradas en `NQC_ARCHIVE_RPC` ni `NQC_TRIPORT_API_KEY` en esta ejecución.

## Alternativa de snapshot: aún no aprobada como solución

El índice del buscador para el explorador oficial enumera Archive PathDB de
28 de septiembre y 9 de octubre, aproximadamente 1.2 y 1.31 TB. La página actual
de Robinhood, en cambio, describe únicamente snapshots podados. No se obtuvieron
metadatos, manifiesto, altura, retención ni checksums del archivo: el índice es
una pista, no evidencia de una base utilizable.

La revisión examinada es `OffchainLabs/go-ethereum` en
`f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88`, submódulo del Nitro fijado por NQC037.
Se preservan cuatro archivos originales y sus licencias en `vendor/geth`.
`SOURCE_REVIEW.json` enlaza los símbolos y hashes reproducibles.
La observación de PathDB se limita a esta revisión y al acceso directo con el
nodo situado en una altura posterior. No demuestra qué software utiliza Triport,
ni descarta restaurar una copia y reconstruir o retroceder su estado. Esa ruta
requiere comprobar primero datos disponibles, retención y recursos; no se ejecutó.

## Alcance de aceptación

Incluso ocho lecturas válidas probarían un paquete parcial contra raíces
observadas. Todavía faltarían la autenticación canónica independiente, el estado
completo necesario para ejecutar `tx0`, su replay Nitro y la posición exacta
anterior a `txIndex=1`. Los valores del cierre del padre no se presentan como ese
preestado. Ninguna puerta de admisión se abre: `commercial_admission=false`,
0/11 slots autenticados en la posición exacta y P&L realizado NQC de cero.

## Validación

```sh
python -m unittest discover -s migration/experiments/nqc-038-archive-access -p 'test_*.py' -v
python -m unittest discover -s migration/experiments/nqc-037-historical-state/tests -v
python migration/verify_isolation.py
python -m unittest migration/test_isolation.py -v
```

Los controles del transporte son simulaciones offline: no sustituyen respuestas
de Robinhood. El resultado efectivo y las comprobaciones están en `RESULTS.json`;
las fuentes y sus límites, en `SOURCES.json`.
