# NQC050 — ejecución criptográfica offline sin dependencias externas

**19 de octubre de 2026.** Base: NQC049 `0028a70364d19fc7151f8dd5169d29a35f9e30cf`. Rama: `research/nqc-050-openssl-crypto-overlay-20261019`. Solo archivos nuevos de este experimento; no cambia NQC037–049, `main`, workflows, despliegues ni credenciales.

## Resultado que sí se obtuvo

El ejecutor Python actual no tiene paquetes `rlp` ni `Crypto` instalados y no resuelve `github.com` por DNS. Sin embargo, su OpenSSL disponible mediante `hashlib.new('keccak-256', data)` sí implementa **Keccak-256 real**. Las pruebas contra los vectores independientes de cadena vacía y `abc` aprobaron; se comprobó explícitamente que Keccak-256 **no** es la variante NIST `sha3_256`.

`compat/rlp.py` ofrece solo la función `rlp.encode` requerida por la cabecera NQC037 y rechaza tipos inválidos. `compat/Crypto/Hash/keccak.py` ofrece la interfaz `keccak.new(digest_bits=256,data=bytes)` que utiliza la fuente fijada, respaldada por **OpenSSL**, sin implementar criptografía nueva ni sustituirla por SHA3. Si OpenSSL carece de ese algoritmo, detiene la ejecución; no activa fallback.

Se ejecutaron **11/11 pruebas de compatibilidad**, y se calculó de nuevo el hash RLP/Keccak de las dos cabeceras **ya conservadas** en NQC037:

- Padre **66744161**, hash calculado igual al observado: `0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917`.
- Objetivo **66744162**, hash calculado igual al observado: `0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7`.
- `parentHash` del objetivo coincide con el hash del padre; al modificar un campo, el cálculo dejó de coincidir.

Las **4/4 pruebas de observaciones históricas** también aprobaron. Los valores transcritos en `parent_header_rehash.py` y `test_saved_headers.py` proceden de los inputs ya fijados: blobs Git `d8576f0...` y `8445e1f...`. Es una **autocomprobación criptográfica de datos previos**, no una nueva prueba de estado, ni una certificación independiente de canonicidad, ni la raíz del preestado exacto `txIndex1`. No se reconsultaron los blobs de NQC036.

## Integración original: alcance real

`offline_run.py` instala estas dos interfaces de compatibilidad **solo dentro del proceso**, identifica el origen de los módulos, utiliza el control de hashes del puente original NQC049 y, si dispone de checkout íntegro verificado, intenta importar el `verify.py` original y llamar a `validate_header`. Después inspecciona el journal **DRY_RUN** mediante `offline_bridge.audit_repository`, sin red ni transporte.

**Esa ruta completa NO se ejecutó:** el contenedor actual no dispone del checkout íntegro. La prueba explícita con un directorio temporal incompleto devolvió `BLOCKED_PINNED_SOURCE_OR_PLAN`, código de salida 2 y cero solicitudes de red. Ninguna simulación sustituye al `validate_step` histórico original ni acredita pruebas Merkle reales. Se volvió a ejecutar la suite offline NQC049 y aprobó 22/22 casos; estos casos ya existían, no se suman de nuevo como evidencia histórica.

Se verificó desde GitHub que **los ocho archivos de código publicados coinciden byte por byte con los scripts probados localmente**, por Git blob SHA. La lista íntegra y los límites constan en `VALIDATION.json` y `STATUS.json`.

## Comandos exclusivamente offline

Para un futuro checkout íntegro en un entorno autorizado (no se necesita instalar nada desde el Android del usuario):

```sh
python -m unittest discover -s migration/experiments/nqc-050-openssl-crypto-overlay -p 'test_*.py' -v
python migration/experiments/nqc-050-openssl-crypto-overlay/offline_run.py --repo-root .
```

El segundo comando **no permite ni realiza RPC**. Contra el fixture DRY_RUN existente con `SIM_ACCEPTED_1` se espera un **bloqueo**, nunca autenticación de la cadena ni permiso de continuar. Si el sistema no tiene OpenSSL Keccak o no conserva los archivos fijados, falla cerrado.

## Bloqueos restantes

No hay todavía un canal soportado para usar la credencial Triport en este ejecutor. El registro de consumo sigue sin integración LIVE completa con el verificador NQC037; faltan persistencia y exclusión operativa para respuestas reales y un checkout íntegro confiable. Ni el tablero Android LIVE ni la documentación de `eth_getProof` acreditan una consulta en nuestro bloque exacto.

**Estado exacto:** 0/8 consultas Triport autenticadas utilizadas, **cero pruebas históricas de estado adquiridas**, **0/11 slots del preestado exacto autenticados**, `commercial_admission=false`. No se autoriza iniciar el plan fuera del contador durable. Tampoco están demostrados canonicidad/finalidad independientes, witness completo, configuración histórica Nitro, replay económico o beneficio neto.

**Siguiente movimiento útil:** obtener de forma autorizada un checkout íntegro en un ejecutor confiable y concluir allí la ejecución del `validate_step` real sobre los archivos ya guardados; después resolver el canal de clave y el registro único **antes** de gastar una de las ocho lecturas. No más pruebas sintéticas como sustituto de evidencia histórica.
