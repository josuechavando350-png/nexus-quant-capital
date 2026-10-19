# NQC039 — cuenta activa; ejecución local preparada

El usuario autorizó la prueba gratuita y completó el registro de Triport. Se
verificó en su panel que la suscripción **Free** está activa y existe una clave.
No se creó una suscripción de pago ni una factura. Se conserva la autorización
para hasta ocho lecturas secuenciales del plan NQC038.

## Bloqueo observado

El mecanismo documentado de archivos compartidos entre navegador y ejecutor no
entregó el archivo temporal al ejecutor. Se comprobó la ruta indicada y se esperó
su sincronización; no apareció. La copia temporal del navegador se eliminó, la
clave se volvió a ocultar y el portapapeles se limpió. La clave no se imprimió,
no está en este repositorio y no se incluye en el exportador.

El panel no expone herramientas WebMCP. La página del método ofrece ejemplos,
sin un formulario para ejecutar nuestras solicitudes. La búsqueda de un plugin
Triport no devolvió resultados. No se reemplazó este límite por una transferencia
a otro servicio. **En NQC039 se enviaron cero consultas RPC y se adquirieron cero
pruebas históricas.** El fallo observado no prueba que Triport rechace el bloque.

## Ejecutar la adquisición

`NQC039_EXPORTADOR.pyz` contiene las solicitudes fijas y el verificador ya probado
de NQC037/038. Requiere Python 3.10 o posterior y las dos dependencias indicadas.
Puede ejecutarse en un entorno virtual existente. Desde la carpeta de descarga:

```sh
python -m pip install rlp==5.0.0 pycryptodome==4.0.1
python NQC039_EXPORTADOR.pyz
```

El programa pide la clave mediante entrada oculta en una terminal interactiva.
La clave no se coloca en el comando ni se guarda en archivos. Hace hasta ocho
lecturas, sin reintentos ni cambios automáticos de bloque, y verifica cada
respuesta antes de avanzar. Usa el mismo endpoint `https://triport.io/rpc/robinhood`.

Al terminar genera una carpeta `nqc039-evidencia-...` y un ZIP con el mismo
nombre. Ese ZIP es el archivo a compartir para continuar la revisión. También
se genera cuando una respuesta es rechazada; `FAILURE.json` explica dónde se
detuvo. Las respuestas de prueba deben corresponder a las raíces y bloques
fijados. El exportador rechaza una respuesta que refleje la clave antes de
persistirla y vuelve a comprobar la ausencia de la clave antes de crear el ZIP.

Para inspeccionar las solicitudes sin clave ni conexión:

```sh
python NQC039_EXPORTADOR.pyz --plan
```

La integridad interna se verifica con SHA-256 antes de cargar los archivos. Esto
detecta diferencias accidentales respecto del manifiesto incluido; no constituye
una firma independiente del autor. `build_exporter.py` permite reconstruir el
ejecutable con los archivos originales listados en `PACKAGE_MANIFEST.json`.

## Alcance

Una adquisición aceptada sigue siendo un paquete parcial contra raíces
observadas. No es por sí sola el preestado exacto de txIndex=1, ni un replay Nitro,
ni una prueba independiente de canonicidad. `commercial_admission=false`.

Las versiones de dependencias coinciden con el entorno de validación y se
comprobaron en sus publicaciones de PyPI:

- https://pypi.org/project/rlp/5.0.0/
- https://pypi.org/project/pycryptodome/4.0.1/

NQC037 y NQC038 se incluyen sin modificaciones en el paquete. El motor R5 y
los experimentos anteriores permanecen intactos. La validación de NQC039 es
offline y está registrada en `VALIDATION.json`; no se presenta como adquisición.
