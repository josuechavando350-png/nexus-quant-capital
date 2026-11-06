# Publicación de código autorizada

Rama: `NQC-defensive`, en `josuechavando350-png/nexus-quant-capital`. El nombre solicitado con un espacio se adapta al formato admitido por Git.

La versión 0.2.1 se publicó en el commit `7faa815497b5c0e9cc81c7626ffe713b12dfacc1`, con 104 pruebas del paquete y 9 de aislamiento aprobadas. Acepta descendientes de la base fijada únicamente si los cambios permanecen dentro de las rutas de defensa autorizadas. También rechaza cambios fuera de alcance en el árbol de trabajo.

La versión 0.3.0 se publicó en `ac5c79c5ac099954c4815586400cd7f2a7bf83c5`. Añade el consumidor local de bytes admitidos, su comando `read-json`, verificación de su evento de auditoría y comprobación del manifiesto real. Su validación consta de 123 pruebas del paquete y 9 de aislamiento.

La versión 0.4.0 se publicó en `8b83b57b3117c9efff67129c67da593c46cde5de`. Añade exportaciones paginadas y un verificador secuencial con checkpoint final fijo, 25 pruebas nuevas y comprobación de 10.003 registros en 20 páginas. Total: 148 pruebas del paquete y 9 de aislamiento.

La versión 0.5.0 se publicó en `cb1aac470e75c436dd4fd00e842437409898635b`. Añade el testigo local de checkpoints, su CLI y comprobación opcional dentro de las transacciones del motor, con 25 pruebas nuevas. Total: 173 pruebas del paquete y 9 de aislamiento.

La versión 0.6.0 se publicó en `74f0f9a21e66d96d167e88b1c677786257f47f6d`. Agrega archivo local por hash, escrituras sincronizadas sin reemplazo, manifiestos canónicos, relectura antes de avanzar el testigo y recuperación de confirmaciones perdidas. Añade 30 pruebas: total 203 del paquete y 9 de aislamiento. Su padre es la publicación 0.5.0. No activa servicios ni elimina historial.

La versión 0.7.0 se publicó en `662d8497fa9696514b4f19362193a1e521800f10`. Agrega cobertura continua entre manifiestos, recibos inicial/final fijados fuera del catálogo, correspondencia exacta con revisiones del testigo y relectura de todas las páginas. Añade 24 pruebas: total 227 del paquete y 9 de aislamiento. Su padre es la publicación 0.6.0. La cobertura local no habilita borrado, retención ni activación productiva.

La versión 0.8.0 se publicó en `d154aeed5b92cbdefe55f680be580c1742abccba`. Agrega inventario acotado de objetos y referencias, verificación de catálogos seleccionados contra recibos externos, tamaños lógicos sin duplicar archivos compartidos e incidencias para referencias faltantes. Añade 28 pruebas: total 255 del paquete y 9 de aislamiento. Su padre es la publicación 0.7.0. Las consultas conservan archivos y checkpoints; un objeto fuera de la selección no se considera automáticamente un huérfano ni se elimina.

La versión 0.9.0 agrega presupuesto persistente con hash externo, coordinación de escritores con bloqueo del directorio, conteo de archivos reales y reintento idéntico sin copia temporal adicional. Páginas, manifiestos y catálogos comparten el control. Añade 30 pruebas: total 285 del paquete y 9 de aislamiento. Su padre es la publicación 0.8.0. Se prueban procesos concurrentes y salidas abruptas; no se borran evidencias ni se activa producción.

Se conservan `main`, las demás ramas, los bytes originales de Census y los workflows deshabilitados. Publicar esta rama no activa un servicio, trading ni despliegue. Los informes de 0.2.0 corresponden a la entrega local anterior.

La entrega 0.10.0 se valida sobre el padre `c8724ba6d9a3ebeed98ddc399ca525dcb3b7c3fd` para publicar únicamente en la misma rama. Agrega los dos catálogos nuevos y la cadena local ManagedIntegrity, sin activar servicios ni cambiar fuentes originales. El commit final se comprueba mediante el ref remoto y la igualdad del árbol publicado con el árbol probado.

La entrega 0.11.0 se valida sobre `6c64cbd6c0da84411e6b90a8ae1631239847e5af` para publicar solo en `NQC-defensive`. Agrega autenticación JSONL, casos compartidos y evaluación explícita. SuperHunter permanece separado.

La entrega 0.12.0 se valida sobre `02d480705e632768f5b670f508dc13bf830a19d5` y se publica solo en `NQC-defensive`. Añade adaptadores OpenSSH/journald y deduplicación nativa con evaluación de formatos; sin fusionar otras ramas ni activar servicios.

La entrega 0.13.0 se valida sobre `ed8bbb6ec3b5b17706fda41f1e277acdd0e3ac4e` para publicar exclusivamente en `NQC-defensive`. Agrega evidencia preservada de casos de autenticación y verificación offline, sin fusionar otras ramas ni activar producción.

La entrega 0.14.0 se valida sobre `ea3018a7464414ab9a10197674d5f4a07a4bad1a` para publicar solo en `NQC-defensive`. Agrega revisión local autenticada por credenciales y ligada a evidencia, sin mezclar SuperHunter ni activar servicios.

La entrega 0.15.0 se valida sobre `b3b837316eb245fd6a2991a9a40aa08cc4675ba3` para publicar solo en `NQC-defensive`. Conecta gestión transaccional de credenciales a revisión de casos, preserva historia 0.14 y no activa servicios.

La entrega 0.16.0 se valida sobre `58f49915374a504a6f20340576767542a4a4c508` para publicar únicamente en `NQC-defensive`. Añade caducidad configurada y control persistente del reloj; conserva el historial 0.15 y no activa servicios.

La entrega 0.17.0 se valida sobre `5187d0ab57a26ce228d24cf2f3582fd696d92a64` y se publica solo en `NQC-defensive`. Añade expedientes e informes offline y cálculo verificable de avance, conservando los registros anteriores. No activa servicios.

La entrega 0.18.0 se valida sobre `4ad9d858d1277fbd2686968856fa73ab39250433` y se publica únicamente en `NQC-defensive`. Añade declaraciones Ed25519 del expediente con verificación pública, sin alterar los historiales ni activar producción.

La entrega 0.19.0 se valida sobre `2ed8de3125843c5932d05e850bb62a51b21b3d7d`. Publica registro de claves y receptor local con 683 pruebas del paquete y 9 de aislamiento; diez criterios de aceptación aprobados. La prueba prolongada sigue en curso y no se cuenta aquí como aprobada.

La entrega 0.20.0 se valida sobre `b28c356de54c6fbffacb199c7ddc1bd7b30e0948`. Reutiliza reconstrucciones inmutables del registro con relectura por llamada y conserva informes idénticos a 0.19. Pasan 698 pruebas del paquete y 9 de aislamiento; cinco criterios del bloque. La prueba prolongada del baseline sigue pendiente y no se cuenta como aprobada.

La entrega 0.21.0 se valida sobre `ad94c2bb4ba903e76cb69f7e07f407df0ce6dc37`. Añade cola explicable de expedientes registrados, política fijada y recomputación. Pasan 743 pruebas del paquete y 9 de aislamiento; seis criterios y 684 variantes de entrada. El paquete instalado reproduce el resultado público. Las dos pruebas prolongadas siguen pendientes al preparar este commit.

La entrega 0.22.0 se valida sobre `d7875badfa2fc4f12b97ff1e1ccb090a7ad342c4`. Incorpora lectura SQLite acotada, cinco criterios aprobados, 760 pruebas del paquete y 9 de aislamiento. Incluye un ensayo concluido de 30 minutos del receptor 0.20, claramente separado del código nuevo. Los otros dos ensayos siguen pendientes al preparar el commit.
