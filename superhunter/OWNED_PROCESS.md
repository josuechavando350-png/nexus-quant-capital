# Cierre de trabajadores propios

Los supervisores QA y de cuotas propias ahora comparten un supervisor de grupos
locales. El supervisor es el único que espera al hijo que acaba de crear con
`start_new_session=True`. En Linux observa su salida con `waitid` y `WNOWAIT`,
conserva al líder sin recolectarlo, comprueba su sesión/grupo, envía SIGKILL al
grupo propio y finalmente recolecta al líder. Se conserva el código de salida
original. Timeout, interrupción o fallo de limpieza impiden devolver éxito.
El plazo se comprueba también cuando la consulta encuentra al hijo ya terminado;
una salida observada después del límite no se convierte en aprobación tardía.

Esto corrige dos problemas comprobados sobre el código anterior:

- La salida normal del supervisor EELS podía dejar un hijo del mismo grupo
  ejecutándose. Un control propio con `fork` reprodujo el comportamiento.
- La ruta de timeout del transporte Geth de cuotas referenciaba `EVMError` sin
  importarlo. El control anterior devolvía `NameError`; ahora mantiene
  `EVMError('EVM_PROCESS_TIMEOUT')`.

La supervisión QA anterior limpiaba después de recolectar al líder. El nuevo
orden conserva la identidad del hijo durante la limpieza. Si se detecta que
otro mecanismo ya lo recolectó, el supervisor bloquea sin enviar señales a un
grupo numérico cuya identidad dejó de comprobarse. Si falla la identificación o
limpieza del grupo, intenta detener únicamente su líder y no devuelve PASS.

Se conservan ocho trabajadores QA, 180 s de pared, 90 s CPU y 2 GiB por
trabajador. El transporte Geth conserva su límite más estricto de 15 s de pared
y los límites del trabajador existente. Los descriptores sellados y los archivos
de salida siguen perteneciendo al llamador. Los límites de bytes continúan en
los consumidores originales; este supervisor no añade entrada de comandos a la
CLI ni recibe objetivos, contratos, calldata o RPC del usuario.

Los tests ejecutan exclusivamente procesos Python propios y dobles explícitos.
Comprueban salida normal, código distinto de cero, timeout, interrupción,
identidad perdida, errores de limpieza, conservación de descriptores y que el
líder todavía sea recolectable al limpiar el grupo. Después de retornar se
comprueba que el líder ya fue recolectado y que el hijo propio está detenido.
La aceptación EVM real sigue siendo un recorrido separado con herramientas fijadas.

Alcance: miembros del mismo grupo, no sesiones que se separen, cgroups,
presupuestos agregados ni aislamiento frente a código nativo hostil. Los
supervisores históricos del compilador y de las capturas nativas no se modifican
ni se recertifican aquí. No se añaden procesos de vigilancia persistentes.

Referencia de la primitiva: [Python 3.12, os.waitid y WNOWAIT](https://docs.python.org/3.12/library/os.html#os.WNOWAIT).
