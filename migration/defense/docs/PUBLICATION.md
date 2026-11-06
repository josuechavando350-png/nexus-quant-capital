# Publicación de código autorizada

Rama: `NQC-defensive`, en `josuechavando350-png/nexus-quant-capital`. El nombre solicitado con un espacio se adapta al formato admitido por Git.

La versión 0.2.1 se publicó en el commit `7faa815497b5c0e9cc81c7626ffe713b12dfacc1`, con 104 pruebas del paquete y 9 de aislamiento aprobadas. Acepta descendientes de la base fijada únicamente si los cambios permanecen dentro de las rutas de defensa autorizadas. También rechaza cambios fuera de alcance en el árbol de trabajo.

La versión 0.3.0 se publicó en `ac5c79c5ac099954c4815586400cd7f2a7bf83c5`. Añade el consumidor local de bytes admitidos, su comando `read-json`, verificación de su evento de auditoría y comprobación del manifiesto real. Su validación consta de 123 pruebas del paquete y 9 de aislamiento.

La versión 0.4.0 se publicó en `8b83b57b3117c9efff67129c67da593c46cde5de`. Añade exportaciones paginadas y un verificador secuencial con checkpoint final fijo, 25 pruebas nuevas y comprobación de 10.003 registros en 20 páginas. Total: 148 pruebas del paquete y 9 de aislamiento.

La versión 0.5.0 añade el testigo local de checkpoints, su CLI y comprobación opcional dentro de las transacciones del motor, con 25 pruebas nuevas. Total: 173 pruebas del paquete y 9 de aislamiento. Su padre es la publicación 0.4.0. Conserva el carácter local: no se activa un servicio remoto ni se habilita borrado de historial.

Se conservan `main`, las demás ramas, los bytes originales de Census y los workflows deshabilitados. Publicar esta rama no activa un servicio, trading ni despliegue. Los informes de 0.2.0 corresponden a la entrega local anterior.
