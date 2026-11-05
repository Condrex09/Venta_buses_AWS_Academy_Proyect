# 🚌 BusDrex - Plataforma de Gestión y Reserva de Pasajes de Buses Interurbanos

**Backend RESTful con Django 5, Django REST Framework, SimpleJWT y MySQL**  
Inspirado en la experiencia de usuario y arquitectura de **Turbus.cl**, **Kupos** y **Recorrido.cl**.

---

### 🎓 Datos del Alumno y Ficha Académica
- **Estudiante:** Benjamin Gómez
- **Sección:** AP-N4-C1
- **Año Académico:** 2026
- **Asignatura:** Programación Back End (INACAP)
- **Evaluación:** Evaluación 2 (Desarrollo Backend con DRF y MySQL)
- **Proyecto Asignado:** Proyecto 4, Reservas de Pasajes de Buses Interurbanos
- **Pie de Página (Footer):** `BusDrex © 2026 | Benjamin Gómez | Sección AP-N4-C1`

---

## 🗄️ Modelo de Datos en Tercera Forma Normal (3FN)

El diseño de base de datos de BusDrex fue completamente refactorizado para cumplir de forma estricta con la **Tercera Forma Normal (3FN)** según el diagrama relacional especificado en [busdrex.dbml](file:///docs/busdrex.dbml).

Para una explicación exhaustiva con diagramas Mermaid, dependencias funcionales, matrices de normalización y justificaciones de diseño para la defensa oral, consulte:
👉 **[Documento de Arquitectura y Modelo 3FN (docs/modelo_3fn.md)](file:///docs/modelo_3fn.md)**

### Las 15 Tablas Normalizadas en MySQL:
1. `usuario`: Cuentas y roles del sistema (`PASAJERO` y `ADMIN_FLOTA`). Se eliminó el campo `rut` para desacoplar al usuario del pasajero físico.
2. `pasajero`: Maestro de personas que viajan (`rut` chileno único y normalizado, `nombre_completo`).
3. `region`: Catálogo de regiones político-administrativas de Chile.
4. `ciudad`: Catálogo de ciudades por región (`region_id` FK).
5. `terminal`: Terminales de buses asociados a una ciudad (`ciudad_id` FK). Se eliminó la dependencia transitiva Terminal $\rightarrow$ Ciudad $\rightarrow$ Región.
6. `ruta`: Conexión direccional entre terminal de origen y destino con duración estimada en minutos (`duracion_minutos`). Restricción `origen != destino`.
7. `bus`: Flota de buses con patente única, modelo, capacidad total y categoría (Semicama, Salón Cama, Premium).
8. `servicio`: Itinerarios programados con fecha/hora de zarpe y tarifas diferenciadas (`tarifa_semicama` y `tarifa_cama`).
9. `asiento`: Inventario atómico con categoría de confort (`SEMICAMA` / `CAMA`) y estado (`DISPONIBLE` / `OCUPADO`). El precio es dinámico.
10. `carro_pasajes`: Carro persistente en MySQL con relación 1 a 1 unívoca con el usuario comprador. Persiste tras logout.
11. `item_carro`: Pasaje incorporado al carro que relaciona Asiento y Pasajero. No guarda precio estático ni descuenta stock.
12. `venta`: Cabecera maestra de la transacción con código UUID único, total histórico y ciclo de vida (`PENDIENTE`, `PAGADO`, `ENTREGADO`, `CANCELADO`).
13. `detalle_venta`: Historial inmutable de pasajes comprados con `precio_unitario` congelado en el checkout.
14. `boleto`: Ticket electrónico con relación OneToOne con `detalle_venta`, UUID único y Hash criptográfico SHA-256.
15. `oferta`: Banners comerciales interactivos administrados por el Administrador de Flota.

### Nota sobre el Reset de Migraciones y Base de Datos (Paso 2)
Durante el proceso de refactorización hacia 3FN, al encontrarse el proyecto en etapa de desarrollo, se realizó un reseteo ordenado de las migraciones anteriores:
1. Se respaldó el código fuente y la base de datos previa.
2. Se eliminaron los archivos de migración intermedios en `apps/*/migrations/` conservando los archivos `__init__.py`.
3. Se recreó la base de datos `busdrex_db` en el servidor MySQL local.
4. Se generaron migraciones limpias desde cero mediante `python manage.py makemigrations` y se aplicaron con `python manage.py migrate`.
5. Se verificó con `SHOW TABLES` que las 15 tablas maestras y sus restricciones UNIQUE coinciden al 100% con `busdrex.dbml`.

---

## 🔒 Reglas de Negocio Implementadas

1. **Exactamente 2 Roles:**
   - `PASAJERO`: Cliente que busca servicios, agrega pasajes a su carro, hace checkout, paga y visualiza sus boletos. Todo registro público crea estrictamente este rol.
   - `ADMIN_FLOTA`: Acceso al panel de control, Swagger UI en `/api/docs/`, CRUD de flota, servicios, itinerarios, ofertas y auditoría de ventas.
2. **Carro Persistente 1 a 1:**
   - Cada usuario posee un único `CarroPasajes` en MySQL que sobrevive al cierre de sesión (logout).
   - Añadir asientos al carro NO descuenta stock de asientos.
   - Si el RUT del pasajero ya existe en la base de datos, se reutiliza su registro sin sobreescribir su nombre.
3. **Control Transaccional Atómico y Concurrencia:**
   - **Checkout:** Crea la venta en `PENDIENTE` y congela los precios en `DetalleVenta`. Vacía el carro. No toca el stock.
   - **Pago:** Se ejecuta dentro de `transaction.atomic()` con bloqueo pesimista `select_for_update()` sobre las filas de los asientos. Si algún asiento fue tomado concurrentemente, se ejecuta rollback total y se devuelve error HTTP 400/409 sin modificar el stock. Si todos están libres, pasan a `OCUPADO`, la venta a `PAGADO` y se emiten los boletos electrónicos.
   - **Cancelación:** Si la venta estaba `PAGADA` y el bus aún no zarpa, los asientos regresan a `DISPONIBLE` y los boletos pasan a `ANULADO`. Operación idempotente. Cancelar una orden `PENDIENTE` no altera el stock.
4. **Protección de Datos Históricos (`models.PROTECT`):**
   - No se pueden eliminar registros con dependencias históricas (ej. ciudades con terminales, asientos con ventas, pasajeros con compras).
   - Las vistas capturan `ProtectedError` y retornan una respuesta clara **HTTP 409 Conflict**.
5. **Seguridad y Rutas:**
   - Swagger UI (`/api/docs/`) accesible exclusivamente para administradores.
   - Redirección automática de cualquier ruta inexistente a la portada principal `/` (sin páginas 404 por defecto).
   - Credenciales completamente parametrizadas desde variables de entorno (`.env`).

---

## 🚀 Puesta en Marcha Local

### 1. Prerrequisitos
- Python 3.10 o superior (ej. Python 3.14).
- Servidor MySQL 8.0 en ejecución en puerto 3306.

### 2. Configuración del Entorno Virtual y Dependencias
```bash
# Crear y activar entorno virtual
python -m venv env
.\env\Scripts\activate

# Instalar librerías requeridas
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno (`.env`)
Crear el archivo `.env` en la raíz del proyecto con la siguiente estructura:
```env
DEBUG=True
SECRET_KEY=busdrex-evaluacion2-inacap-2026-secret-key-benjamin-gomez
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=custom_mysql
DB_NAME=busdrex_db
DB_USER=root
DB_PASSWORD=tu_password_mysql
DB_HOST=127.0.0.1
DB_PORT=3306

ADMIN_USERNAME=admin_flota
ADMIN_PASSWORD=Admin1234!
PASAJERO_USERNAME=pasajero_demo
PASAJERO_PASSWORD=Pasajero1234!
```

### 4. Recrear Base de Datos y Aplicar Migraciones
```bash
# Crear base de datos en MySQL
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS busdrex_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Generar y aplicar migraciones
python manage.py makemigrations
python manage.py migrate

# Cargar semillero de datos iniciales en 3FN
python manage.py poblar_busdrex
```

### 5. Iniciar Servidor de Desarrollo
```bash
python manage.py runserver
```

---

## 🧪 Ejecución de Pruebas Automatizadas
Para verificar la suite completa de pruebas unitarias y de integración que validan la 3FN, concurrencia, bloqueo pesimista y respuestas HTTP 409:
```bash
python manage.py test
```

---

## 🌐 Credenciales de Demostración
- **Administrador de Flota:** Usuario: `admin_flota` | Contraseña: `Admin1234!` (Acceso a `/panel/` y `/api/docs/`)
- **Pasajero Demo:** Usuario: `pasajero_demo` | Contraseña: `Pasajero1234!` (Acceso a cotización, carro y boletos)
