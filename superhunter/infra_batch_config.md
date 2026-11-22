# Verificación offline de configuración de NQC

**Cartography (#80).** El parser auténtico de GitHub Actions reconstruye las referencias de acciones y los permisos declarados en los 106 workflows históricos deshabilitados. NQC contrasta cada decisión con otra lectura de las líneas de declaración de esos archivos, cuyas identidades están ligadas al árbol `1cc2c2f05820eb707d7e71b0a1ae54e944f7fe45`. El resultado permite seleccionar revisiones explícitas de configuración. En 119 jobs se registran 202 referencias distintas por archivo. Catorce archivos contienen 31 referencias por etiqueta y dos archivos declaran ámbitos de escritura. El control en una copia temporal reemplaza una revisión por una etiqueta y modifica el permiso de contenido. El producto detecta ambos cambios. Los datos describen configuraciones archivadas y permisos de nivel de workflow. Los tokens efectivos y la configuración actual de GitHub quedan fuera de ese alcance.

**SSLyze (#66) y testssl.sh (#72).** El recuperador de manifiestos de NQC usa el contexto HTTPS predeterminado de CPython. Se obtiene su primer registro ClientHello mediante SSLObject y dos objetos MemoryBIO. No se establece conexión ni se proporciona clave o certificado. La tabla de testssl.sh asigna los 17 códigos emitidos a los nombres IANA y OpenSSL, contrastados con la API de OpenSSL. NQC consume la copia 5.7 del perfil Mozilla publicada en SSLyze para determinar compatibilidad de versión y suite. Hay tres suites compartidas con el perfil moderno y once con el intermedio. Al restringir el cliente a TLS 1.2, el moderno tiene cero coincidencias y el intermedio conserva ocho. Esta operación verifica la oferta inicial; no autentica un servidor, negocia una sesión ni acredita el cumplimiento integral del perfil Mozilla.

## Fuentes y entorno

Las revisiones y los hashes de todos los datos de cada proveedor están en [el recibo](product_supply/infra_batch_config.json). Se observaron CPython 3.12 y OpenSSL 3.5.8. Un runtime con distinta oferta TLS puede producir una observación diferente. Los bytes aleatorios del ClientHello se descartan tras extraer sus vectores.

El worker carga Cartography y los módulos Python puros de PyYAML en un proceso aislado sin red. Para este lote se cotejaron los 17 archivos usados con la rueda PyYAML 6.0.3 de CPython 3.12 para Linux x86-64, SHA-256 `ba1cc08a7ccde2d2ec775841541641e4548226580ab850948cbfda66a1befcdc`. El conjunto de archivos Python debe coincidir con `05780a44b9c038a882c0a22e76719a5117c514ebb41f98f9e4f4cb96cc6dd73e`. Los metadatos de la rueda indican MIT y no enumeran dependencias de ejecución. El archivo de licencia tiene el SHA-256 `8d3928f9dc4490fd635707cb88eb26bd764102a7282954307d3e5167a577e8a4`. La rueda no se distribuye dentro de NQC.

## Reproducir

Requiere los tres checkouts fijados, Python 3.12 con PyYAML 6.0.3 y soporte Linux para unshare. Con el entorno citado y desde la raíz de producto:

```sh
python3.12 -B -m unittest superhunter.tests.test_infra_batch_config
python3.12 -B - <<'PY'
from pathlib import Path
from superhunter.product_config_batch import review
from superhunter.safe_io import canonical
from superhunter.product_review import sha

result = canonical(review(Path('upstream')))
assert result == Path('superhunter/product_supply/infra_batch_config.json').read_bytes()
print(sha(result))
PY
```

El recibo reproducido tiene SHA-256 `55c054d6ec1bf8426deb65c0fad7a5b35a3b7879cc1b05bedc8da6059c311f06`.
