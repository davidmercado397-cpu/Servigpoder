# Guía de validación QA desde cero

Marque cada casilla al validarla. Los **valores esperados** corresponden a los archivos de prueba
usados en el desarrollo (septiembre 2026):

- `MATRIZ PROGRAMACION (3).xlsx`: matriz comercial
- `GenConsultaMaestroGrid (3).xlsx`: horarios de SIESA
- `ReporteAsignacionResumido (6).xlsx`: programación del 15 al 30 de septiembre

Si usa otros archivos, los números cambian pero los comportamientos deben ser los mismos.

---

## 0. Preparación: base de datos vacía

> ⚠ Esto borra todos los datos de la base local.

```bash
docker compose down -v
docker compose up -d --build
```

- [ ] Los 3 contenedores quedan `healthy` / `Up` (`docker compose ps`).
- [ ] En los logs del backend aparecen las migraciones `0001` a `0004` y "Seed completado" (`docker compose logs backend`).
- [ ] http://localhost:3000 redirige a `/login`.

### Ingreso y portal (plataforma)
- [ ] Usuario y contraseña correctos llevan al paso 2; **no** hay acceso sin el código.
- [ ] Primer ingreso: se muestra el QR; escanearlo con Microsoft/Google Authenticator; el código activa la MFA.
- [ ] Se muestran **10 códigos de recuperación** una sola vez; "Copiar códigos" funciona.
- [ ] Ingresos siguientes piden solo el código de 6 dígitos; un código incorrecto se rechaza.
- [ ] "No tengo mi teléfono": un código de recuperación permite entrar **una sola vez**.
- [ ] 5 códigos incorrectos seguidos bloquean temporalmente.
- [ ] El portal (`/`) muestra la tarjeta **Capacidad Operativa** y, para el administrador, Administración (Usuarios, Roles, Auditoría).
- [ ] Un usuario sin permisos de Capacidad no ve la tarjeta y la API le responde 403.
- [ ] 30 minutos sin actividad: la siguiente acción lleva a `/login` con el aviso "Su sesión se cerró por inactividad".

---

## F1. Maestros, matriz comercial y carga de programación

### Acceso
- [ ] Ingresar con `admin` y `ADMIN_PASSWORD` del `.env`: lleva a Inicio.
- [ ] Una contraseña errada muestra "Usuario o contraseña incorrectos" (no dice si el usuario existe).

### Horarios de SIESA (Capacidad → Maestros → Horarios SIESA)
- [ ] Cargar `GenConsultaMaestroGrid`: **64 horarios cargados**.
- [ ] `T.P.` y `TURNO PARTIDO` muestran **dos franjas** (05:30–12:00 y 14:30–20:30).
- [ ] `Z` y `L` aparecen como **Descanso**.
- [ ] `08:00 - 22:00*` muestra 08:00–20:00 (se toma la entrada y salida registradas).
- [ ] Subir un archivo que no es Excel (un .pdf renombrado a .xlsx) es rechazado con un mensaje claro.

### Novedades (Capacidad → Maestros → Novedades)
- [ ] Existen VAC, PRV, LNR, LRM, LIC, LUT, IEG, AT, AUS, IND, IND NOCHE, PSA y PSB, todas con "Requiere cubrimiento".
- [ ] Se puede agregar una novedad nueva y desmarcar "Requiere cubrimiento".

### Matriz comercial (Capacidad → Configuración → Matriz comercial)
- [ ] "Importar matriz desde Excel" con mes **Septiembre 2026**: aparece el aviso *"198-3: Hombres '15,' interpretado como 1,5"*.
- [ ] Resumen: **738 puestos**, **57 por revisar** y **22 excluidos**.
- [ ] Los repetidos quedan separados: 86 / 86-1, 95 / 95-1, 99 / 99-1 / 99-2 y 135 / 135-1.
- [ ] El puesto **198-3** tiene 1,5 hombres.
- [ ] Los escoltas, coordinadores y supervisores (por ejemplo `14-J` y `166-x`) aparecen en gris como **Excluido**.
- [ ] Un puesto "TERNA NORMAL" (por ejemplo `25`) muestra **L-D 06:00–18:00 · L-D 18:00–06:00** e **incluye festivos: Sí**.
- [ ] Un puesto de recepción L-V con sábados (por ejemplo `3`) muestra **L-V 06–18 · S 06–14** e **incluye festivos: No**.
- [ ] **Casilla "¿Incluye festivos?" en la tabla**: al marcarla o desmarcarla se guarda al instante, y al recargar la página se mantiene.
- [ ] En el panel del puesto, la pregunta de festivos con las opciones Sí/No coincide con la tabla.
- [ ] El calendario del puesto marca en rojo los festivos. Con "No" incluye festivos, esos días quedan en **—**.
- [ ] Editar franjas (días, horas, cantidad), guardar, y el calendario se recalcula.
- [ ] Una **excepción** "sin servicio" en una fecha deja ese día en 0 horas; al eliminarla vuelve a su valor.
- [ ] El filtro "Solo los que requieren revisión" muestra 57. "Guardar y marcar revisado" lo quita de la lista.
- [ ] **Proyectar al mes siguiente**: crea Octubre 2026 en **borrador** con los mismos 738 puestos. Un cambio en octubre **no** altera septiembre.
- [ ] Proyectar dos veces el mismo mes muestra "Ya existe la matriz de 10/2026".
- [ ] Un puesto marcado **inactivo** en Maestros no se proyecta al mes siguiente.
- [ ] "Cerrar mes" pide confirmación. Después, la matriz ya no se puede editar (campos y casillas bloqueados).

### Programación SIESA (Capacidad → Operación → Programación SIESA)
- [ ] Subir `ReporteAsignacionResumido`: **2.181 filas**, **1.870 empleados**, **724 puestos**.
- [ ] Clases: turnos 19.639 · descansos 9.030 · novedades 1.358 · **ninguno sin interpretar**.
- [ ] Aviso de puestos sin equivalencia, con enlace a Maestros.

### Puestos por aclarar (Capacidad → Maestros → Puestos por aclarar)
- [ ] **23 "Sin equivalencia"** y **18 "Verificar"** (SENA `283-15-x` → `283-15x`).
- [ ] "Confirmar 283-151" (u otro) pasa la fila a resuelta.
- [ ] Asignar un puesto con el selector la quita de la lista.
- [ ] `01-2` **no** se cruza con el puesto `12` (la ubicación debe coincidir).

---

## F2. Motor de cobertura, tablero y vista por puesto

### Tablero (Capacidad → Operación → Cobertura)
- [ ] Al subir la programación el análisis se calcula solo. Si no hay matriz del mes, muestra el aviso.
- [ ] Cobertura **≈ 89,6 %**, horas descubiertas ≈ 24.121 y en exceso ≈ 8.823 (antes de aclarar puestos).
- [ ] Los indicadores filtran la tabla al hacer clic (con hueco, con exceso, titulares ≠ hombres, vendidos sin programar).
- [ ] La tabla por ciudad filtra la lista de puestos al hacer clic en una ciudad.
- [ ] Buscador y orden (más descubiertas, más exceso, código) funcionan.
- [ ] "Exportar a Excel" descarga un archivo con las hojas **Resumen**, **Puestos** y **Hallazgos por día**.
- [ ] Al editar la matriz aparece "⚠ La matriz comercial cambió después del análisis". "Recalcular" lo quita.
- [ ] Después de asignar los puestos por aclarar y recalcular, la cobertura **sube** y "Vendidos sin programar" **baja**.

### Vista por puesto (clic en un puesto)
- [ ] El calendario muestra personas × días. **D** = 06–18, **N** = 18–06, las novedades en amarillo y los descansos en gris.
- [ ] Cada persona dice si es **titular** o **apoyo (titular en X)**.
- [ ] La fila "Resultado del día" muestra ✓ ▼ ▲ ◆ con tooltip ("Falta 1 de 18:00 a 06:00").
- [ ] La tabla "Hallazgos por día" coincide con el calendario.
- [ ] Casos de referencia (ver *Sugerencias de revisión* al final): **220**, **291**, **25**.

---

## F3. Cubrimientos, bandeja de nómina y bolsas

### Cubrimientos (Capacidad → Operación → Cubrimientos)
- [ ] Total **382**: **264 justificados** y **118 pendientes**.
- [ ] Un justificado por novedad dice *"Cubre novedad de NOMBRE (VAC/LNR/IND…)"*.
- [ ] Un justificado por descanso dice *"Relevo del descanso de NOMBRE (Z/L)"*.
- [ ] Los filtros "Solo los que generan exceso" y "Solo doble turno" funcionan.
- [ ] Con el usuario de **Nómina**: aprobar uno lo pasa a "Aprobados" con su nombre.
- [ ] **Rechazar** exige comentario (sin comentario no se guarda).
- [ ] Selección múltiple: aprobar o rechazar varios a la vez.
- [ ] "Deshacer" devuelve al estado automático.
- [ ] **Recalcular la cobertura NO borra** las aprobaciones ni los rechazos.
- [ ] Con el usuario **Programador**: ve los cubrimientos pero **no** tiene botones de aprobar o rechazar (y la API responde 403).

### Personas en bolsa (Capacidad → Operación → Personas en bolsa)
- [ ] Por defecto solo bolsas **05 y 06**: **≈ 85 personas**, ≈ 3.954 horas.
- [ ] "Incluir todas las bolsas" agrega 07 incapacitados y 08 vacaciones (≈ 105 personas).
- [ ] Una persona que el mismo día está en bolsa y cubre un puesto **no** cuenta ese día.

---

## F4. Histórico, novedades de programación, alertas y parámetros

### Histórico (Capacidad → Operación → Histórico y novedades)
- [ ] Cada carga aparece agrupada por mes con su cobertura.
- [ ] Modifique algunas celdas del Excel de SIESA (por ejemplo cambie un turno por `[VAC]`) y súbalo de nuevo como otra carga del mismo mes.
- [ ] "Comparar con #N" lista los cambios **agregados / eliminados / cambiados** con antes y después.
- [ ] La tabla "Impacto en la cobertura" muestra los puestos cuya cobertura cambió (▲ empeora / ▼ mejora).

### Alertas (Inicio)
- [ ] Aparecen ordenadas: críticas → advertencias → información.
- [ ] "Cobertura del X %" (crítica) cuando está por debajo del umbral.
- [ ] "N puestos con hueco entre hoy y …": "Ver" lista puesto, fecha y franjas, con enlace al calendario del puesto.
- [ ] "Puestos de SIESA por aclarar", "cubrimientos pendientes" y "matriz en borrador" aparecen cuando corresponde.
- [ ] Al aprobar la matriz, la alerta de borrador desaparece.

### Parámetros (Administración → Parámetros de alertas)
- [ ] Cambiar "Cobertura mínima" a 85: la alerta crítica de cobertura desaparece. Volver a 95: reaparece.
- [ ] Un valor no numérico es rechazado.
- [ ] Con el usuario Programador o Nómina no aparece el menú de Parámetros.

---

## F5. Seguridad, usuarios y puesta en producción

### Usuarios y roles
- [ ] Crear los usuarios Programador y Nómina desde Administración → Usuarios (la contraseña asignada es **temporal**).
- [ ] En su primer ingreso configuran MFA y quedan obligados a **cambiar la contraseña** (no pueden ver nada más).
- [ ] "Restablecer MFA" de un usuario cierra su sesión y le pide configurar la MFA de nuevo.
- [ ] Seguridad de mi cuenta: cambiar contraseña (cierra otras sesiones) y generar códigos de recuperación nuevos.
- [ ] Administración → Auditoría muestra ingresos (con método MFA), fallidos, bloqueos y cambios, con filtros.
- [ ] Una contraseña de menos de 10 caracteres, o sin números, es rechazada.
- [ ] Cada rol solo ve su menú. Por URL directa a una pantalla sin permiso, los datos no cargan.
- [ ] Crear un rol nuevo ("Consulta" solo con "Ver tablero") y asignarlo: solo ve lo permitido.
- [ ] Desactivar un usuario o cambiarle la contraseña **cierra su sesión abierta**.
- [ ] El rol Administrador no se puede eliminar ni renombrar.

### Seguridad
- [ ] 5 intentos fallidos de login con un usuario: el 6.º responde **"Usuario bloqueado temporalmente"** (15 min).
- [ ] Más de 10 intentos por minuto desde la misma IP: **"Demasiadas solicitudes"**.
- [ ] Un archivo mayor a 15 MB es rechazado.
- [ ] En producción (`ENVIRONMENT=production`), http://localhost:3000/api/docs responde 404.
- [ ] Toda respuesta de la API tiene `success`, `data`, `error` y `meta.request_id`.
- [ ] La tabla `auditoria` registra login, cambios de usuarios, roles, matriz, cargas y decisiones de nómina:
  ```bash
  docker compose exec db psql -U capacidad -d capacidad -c "select fecha, accion, ip from auditoria order by id desc limit 20"
  ```

### Despliegue en Coolify
- [ ] Recurso **Docker Compose** apuntando a GitHub `main`.
- [ ] Variables configuradas: claves nuevas y largas, `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `ADMIN_PASSWORD` de 12+ caracteres.
- [ ] Dominio asignado solo al servicio **frontend** (puerto 3000) con HTTPS. `backend` y `db` **no** expuestos.
- [ ] Tras desplegar, el login funciona por HTTPS y la cookie `sesion` es `Secure`.
- [ ] En la auditoría se registra la **IP real** del usuario (no una 10.x/172.x).
- [ ] Respaldo programado de la base (ver README → Respaldos) y una restauración de prueba exitosa.
- [ ] Un redeploy (push a `main`) aplica migraciones nuevas sin perder datos.

---

## Sugerencias de revisión (casos de negocio)

Casos reales detectados en la programación del 15 al 30 de septiembre. Sirven para confirmar que el sistema dice lo mismo que el equipo de programación sabe de cada puesto:

| Puesto | Ubicación | Qué muestra el sistema | Qué validar |
|---|---|---|---|
| **220** | Parcelación Campestre Colinas de Niza | Hueco y exceso: el 15 falta el turno de día y sobra 1 de noche; el 16 y el 17 falta la noche | ¿Los turnos de esos días están mal programados en SIESA? |
| **291** | C.R. Filandia Etapa 1 | Exceso de noche: 1 persona de más el 21 y el 27, y **2 de más el 26** | ¿Por qué hay 2–3 personas de noche? El cubrimiento del 21 (Ortiz Montes) quedó pendiente |
| **25** | Edificio Seminario | Hueco de día el 15 (el titular Delgado está en vacaciones y nadie lo cubrió) | ¿Se envió reemplazo que no quedó en SIESA? |
| **127-1** | C.R. Mont-Bré (rondero) | Cubrimientos sin motivo de Morales Ospina (titular en 127) los días 17, 18 y 24 | ¿Es un turno adicional autorizado? |
| **99-1** | C.R. Quintas de la Bocana | El puesto con más exceso (396 h): 1,5 hombres presupuestados y 4 titulares | ¿Cambió lo vendido o sobra gente? |
| **04** | Guardas élites | 368 h de exceso contra "SOLO DÍA" en la matriz | ¿La jornada vendida es correcta en la matriz? |
| **09** | Central Servigpoder | 7 titulares contra 3 presupuestados | ¿Actualizar la matriz? |
| **161**, **11** | Parque El Vínculo, Museo INCIVA | Muchas personas contra los hombres presupuestados | Revisar titulares y apoyos |
| **32, 321, 262, 60-1, 60-7…** | Varios | Vendidos sin nadie programado | Casi seguro son códigos distintos en SIESA: resolver en "Puestos por aclarar" |
| **23 puestos por aclarar** | Zonas 01-x, 13, 206-26, 49J, 2843-7G, 283-12-7B, 1221-1, 134-30, 146-14F, 14-2, 206-27, 231-1, 257-28A, 265-1, 270-1, 275-3, 295-1, 79-1 | Sin equivalencia en la matriz | Asignar o marcar como excluidos |
| **57 puestos por revisar** en la matriz | Varios | Hombres que no cuadran con la secuencia (por ejemplo "TURNO 8 HORAS B-A-C" con 3 hombres cuando 6x1 pide 3,5) | Confirmar el presupuesto o corregir la matriz |
