# Revisión de límites del repositorio ampliado

`python -m superhunter review-repository-boundary` comprueba el checkout completo
sin ejecutar su código ni modificar el material histórico. También acepta `--root`
para una copia local. Devuelve `REPOSITORY_BOUNDARY_PASS` o un bloqueo con código
fijo, sin imprimir rutas privadas o contenido de archivos.

## Qué se comprueba

- Árboles Git exactos de `ci/`, `migration/` y `nqc-census/`: 642 archivos, incluidos
  el manifiesto y el verificador de migración. Se conservan bytes, pertenencia y
  modos Git; el hash se reconstruye localmente sin ejecutar comandos del checkout.
- Identidades originales de `README.md`, `AGENTS.md` y `.gitignore`.
- Solo se admiten la raíz `superhunter/` y los tres documentos de continuidad
  nombrados explícitamente, además de los árboles históricos. En SuperHunter se
  admiten fuentes Python, Markdown, JSON, texto y su `.gitignore`, sin modo ejecutable.
- Se rechazan árboles de clientes, workflows activos, dependencias nativas
  incorporadas, enlaces simbólicos, archivos especiales y entradas no revisadas.
- Dos inventarios completos deben coincidir. Se limitan profundidad, número de
  archivos/directorios y tamaños. Las cachés `.pyc` bajo `__pycache__` de SuperHunter
  se cuentan como exclusiones explícitas; no forman parte de la identidad fuente.

Los pins proceden de los árboles originales preservados y cotejados antes de
las reparaciones de PR #54/#55. El nuevo control comprueba la frontera estructural
del repositorio ampliado; no otorga autorización de despliegue ni de ejecución.

## Relación con el verificador histórico

`migration/verify_isolation.py` permanece **byte por byte intacto**. Su contrato
original solo admite el árbol importado y sigue rechazando un checkout ampliado
con SuperHunter. La revisión nueva no cambia ese resultado ni reemplaza su
certificación. El verificador original y sus nueve pruebas se ejecutan por
separado sobre una copia exacta de su ámbito histórico.

Por tanto se pueden afirmar dos resultados concretos: preservación del árbol
histórico y admisión estructural explícita de SuperHunter. La inspección de los
objetos del repositorio de origen, la recertificación Rust/PFT/Census y una
revisión independiente completa siguen pendientes.

## Límites

La comprobación no demuestra que cada archivo Python sea seguro, que no existan
secretos en texto ni que los procesos estén aislados durante su ejecución.
Tampoco es una instantánea atómica frente a un host adversario: las dos lecturas
detectan cambios ordinarios persistentes durante la revisión. Un PASS no habilita
workflows, red, wallets ni acciones externas. Es un control de integridad y ámbito
de fuentes, complementario a QA y a los ensayos nativos.
