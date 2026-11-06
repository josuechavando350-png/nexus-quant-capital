# Continuidad — inventario de estado obtenido desde fuente

Base exacta: `SUPERHUNTER_posiciones_storage_1267.zip`, subdirectorio `codigo/`.
Se añade `solidity_inventory.py` y `tests/test_solidity_inventory.py` al paquete,
sin sustituir módulos, borrar tests anteriores o alterar fuentes nativas.

Nueva ruta: manifiesto externo v4 → lectura completa de fuente → asociación de
las declaraciones de estado → contraste con AST → capas previas de layout/tipos/
posiciones → AuditLog de DIABLO → paquete privado → verificación separada.
El orden interno conserva las comprobaciones previas antes del contraste final;
una contradicción en cualquiera impide producir un resultado favorable.

Control discriminante ya reproducido: AST y layout omiten conjuntamente la última
variable presente en la fuente. El perfil v3 la desconoce y devuelve PRESERVED;
el perfil v4 rechaza el conjunto incompleto. También se comprueba que una mutable
no pueda desaparecer clasificándola falsamente como constant/transient en el AST.

Pruebas nuevas: 49. Los resultados de la suite completa, el parche en segunda
copia y los controles por CLI se registran fuera del código, en VALIDATION.json.
No usar este handoff ni los contadores históricos como recibos de una ejecución.

## Límites que no deben perderse

- No se obtuvo solc ni se ejecutó Solidity/EVM. Se intentaron rutas oficiales de
  binarios y distribución; hubo fallos de DNS/descarga. No atribuir los AST a una
  ejecución del compilador. Instalar y fijar el compilador real sigue pendiente.
- Se trata de un parser de fronteras de miembros y declaraciones para un perfil
  acotado, no de la gramática o semántica completa de Solidity. Los cuerpos de
  métodos se delimitan como opacos. Consultar SOURCE_DECLARATION_INVENTORY.md.
- La correspondencia de un AST con el productor declarado sigue sin autenticarse.
  Una revisión en el perfil no autoriza upgrades ni confirma vulnerabilidades.
- Los catálogos 27/50/25 siguen iguales. No se eleva ninguna capacidad a completa.
- Sin commits remotos, workflows, cuentas, objetivos externos ni transacciones.
  No se ejecutó la suite histórica NQC ni el aislamiento del repositorio completo.
- El acumulado local es mayor que las ramas remotas focalizadas. Aplicar el parche
  exclusivamente sobre la base ZIP1267 o usar el código completo tras revisar sus
  manifiestos. No reemplazar una rama de GitHub sin conciliación de cambios.

## Siguiente comprobación material

Contrastar este perfil y los anteriores con AST/layout obtenidos de una ejecución
real, reproducible y fijada de solc sobre fuentes benignas propias. Mantener los
casos sintéticos claramente separados. No usar resultados suministrados como
prueba de una compilación que no se ha ejecutado.
