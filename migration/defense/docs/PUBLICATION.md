# Publicación de código autorizada

Rama: `NQC-defensive`, en `josuechavando350-png/nexus-quant-capital`. El nombre solicitado con un espacio se adapta al formato admitido por Git.

La versión 0.2.1 se publicó en el commit `7faa815497b5c0e9cc81c7626ffe713b12dfacc1`, con 104 pruebas del paquete y 9 de aislamiento aprobadas. Acepta descendientes de la base fijada únicamente si los cambios permanecen dentro de las rutas de defensa autorizadas. También rechaza cambios fuera de alcance en el árbol de trabajo.

La versión 0.3.0 añade el consumidor local de bytes admitidos, su comando `read-json`, verificación de su evento de auditoría y comprobación del manifiesto real. Su validación consta de 123 pruebas del paquete y 9 de aislamiento. El commit de esta entrega conserva como padre la publicación anterior y solo modifica las rutas de defensa.

Se conservan `main`, las demás ramas, los bytes originales de Census y los workflows deshabilitados. Publicar esta rama no activa un servicio, trading ni despliegue. Los informes de 0.2.0 corresponden a la entrega local anterior.
