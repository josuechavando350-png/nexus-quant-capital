# NQC044 — una prueba de lectura no garantiza cobertura de escritura

Fecha: 2026-10-19. Continuación de NQC043 (`0d0683074fdf1397de9a7d1f6d8641c4ddf3c4e4`). Todo caso ejecutado aquí es **sintético y offline**. Cero consultas RPC, cero pruebas históricas adquiridas, `commercial_admission=false`.

## Resultado concreto

Un trie inventado contiene los slots 9 y 13, con valores 77 y 88, usando claves `keccak256(slot de 32 bytes)`. La prueba del slot 9 tiene dos nodos y el verificador MPT preservado de NQC031/NQC037 valida su lectura. Sin embargo, borrar ese slot con solamente esos nodos falla: al quedar un único hijo, la compactación de la rama necesita decodificar el hermano, cuyo hash sí está comprometido pero cuyos bytes no vienen en la prueba de lectura.

`proof_trial.py` devuelve el hash faltante y `new_root=null`; no busca nodos ni acepta el estado incompleto. Añadir el nodo sintético faltante, tras comprobar su hash, permite completar el borrado. La raíz coincide con un trie de referencia completo y con la fórmula independiente de la única hoja restante, usando el codificador RLP preservado. Los bytes, hashes, pruebas y resultados están en `evidence/SYNTHETIC_WRITE_CASE.json`.

Esto **no demuestra un defecto del verificador de lectura**, ni del proveedor, ni que todo borrado necesite más nodos. En este mismo caso reemplazar el valor funciona con la prueba original. Los controles cubren inserción desde no inclusión, borrado ausente, hoja única, dos ramas restantes, hermano inline, extensión anidada, nodo adicional incorrecto y prueba incompleta. Los casos inline y extensión usan claves artificiales para controlar la geometría, no preimágenes conocidas de slots históricos.

## Contraste con código candidato

Se preserva sin modificaciones `trie/trie.go` de OffchainLabs/go-ethereum, commit `f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88` (blob `1ef2c2f1a66e0d80b324fa87550307ea563d699c`). En `Trie.delete`, la rama con un solo hijo restante resuelve ese hijo antes de decidir la compactación; si falta, propaga el error. Esto concuerda con el mecanismo observado en Python. **No se compiló ni ejecutó Go, ni se identificó el binario histórico de la cadena.** La prueba Python usa `trie` 4.0.0; su algoritmo no equivale a validar toda la implementación Go.

Fuentes candidatas ya preservadas por NQC037: `DeleteRetryable` borra campos y llama `ClearBytes`; `ClearBytes` borra palabras de calldata y longitud. Esto hace pertinente la pregunta de cobertura de borrado, pero no prueba que el tx0 histórico entrara en esa rama. Licencias upstream se conservan en NQC037 (`vendor/go-ethereum__COPYING` y `vendor/go-ethereum__COPYING.LESSER`) y en el encabezado del archivo nuevo. `SOURCE_BINDING.json` fija fuentes y dependencias locales.

## Límite y siguiente tramo verificable

El ensayo opera sobre **un trie crudo**, no ejecuta transacciones, no actualiza automáticamente un storageRoot dentro de su cuenta, no produce un stateRoot de replay, no cubre persistencia de base de datos y no calcula beneficio. La cobertura necesaria depende de las escrituras efectivas y de la forma del trie. Una futura adquisición debe distinguir:

1. Lecturas verificadas contra una raíz, sin asumir canonicidad independiente.
2. Cobertura de las operaciones efectivas: si falta un nodo, detenerse y conservar su hash como requisito, sin raíz provisional aceptada.
3. Actualización del trie de almacenamiento y de la cuenta, ejecución Nitro correcta, configuración histórica y posición txIndex1. Nada de esto se da por resuelto aquí.

El siguiente tramo concreto es comprobar **la cascada almacenamiento → cuenta → raíz de estado en un ejemplo sintético**, conservando el bloqueo cuando falta el hermano de almacenamiento. Ello probaría más código, no el preestado histórico. La adquisición real sigue requiriendo un canal soportado para la credencial y un registro durable inequívoco del consumo. La inspección de las capacidades disponibles en esta iteración no identificó ese canal; no se abrió el panel, no se extrajo una clave, no se repitió la transferencia fallida ni se hicieron llamadas al proveedor. El plan NQC038 permanece intacto y no autoriza lecturas adicionales para hermanos de trie.

## Reproducción

Desde la raíz del repositorio, con las dependencias Python existentes de NQC037 y `trie==4.0.0`:

```sh
python migration/experiments/nqc-044-write-witness/validate.py
```

No requiere conexión de red ni claves. El runner regenera únicamente evidencia en este experimento: 14 pruebas nuevas, 32 del verificador original, 9 de aislamiento y el verificador de aislamiento. Versiones y hashes de las implementaciones Python efectivamente usadas quedan en `RUNTIME.json`; salidas y códigos de retorno en `VALIDATION.json` y logs. No se ejecutaron pruebas Rust, Go, RPC ni replay Nitro: ninguno de esos componentes fue modificado. `MANIFEST.json` cubre los bytes de este experimento salvo sí mismo y cachés.
