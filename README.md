# Miniclase: Apache NiFi — de un CSV a PostgreSQL

Demostración de un flujo ETL con Apache NiFi 2.12: se lee un CSV, se carga en PostgreSQL y los archivos con errores se separan automáticamente.

```
 data/entrada/*.csv ──► [GetFile] ──────┐
                                        ├──► [PutDatabaseRecord] ──► tabla clientes (PostgreSQL)
 Página web ────────► [ListenHTTP] ─────┘            │ failure
                                                     ▼
                                                [PutFile] ──► data/errores/
```

## Inicio rápido

Requisitos: **Docker Desktop** y **Python 3**.

```powershell
docker compose up -d        # esperar 1–2 minutos a que NiFi arranque
python crear_flujo.py       # crea el flujo en NiFi
```

Abrir <http://localhost:18000>, pulsar **✅ Válido** → **Enviar a NiFi** y ver las filas aparecer en la tabla.

## Contenido del proyecto

| Archivo / carpeta | Para qué sirve |
|---|---|
| `docker-compose.yml` | Levanta NiFi, PostgreSQL, la página web (nginx + PostgREST) y Adminer |
| `init.sql` | Crea la tabla `clientes` al iniciar PostgreSQL |
| `drivers/postgresql-42.7.14.jar` | Driver JDBC (NiFi no trae el de PostgreSQL) |
| `muestras/datos.csv` | 5 clientes válidos |
| `muestras/datos_con_error.csv` | Fecha inválida → para mostrar el manejo de errores |
| `muestras/datos_fecha_latina.csv` | Fechas `dd/MM/yyyy` → para mostrar `UpdateRecord` |
| `data/entrada/` | Carpeta que NiFi vigila (aquí se "suelta" el CSV) |
| `data/errores/` | Aquí NiFi deja los archivos que fallaron |
| `crear_flujo.py` | **Plan B:** crea todo el flujo automáticamente |
| `web/` | Página de la demo (`index.html`) y configuración de nginx |

## Datos de acceso

| | |
|---|---|
| NiFi | <https://localhost:8443/nifi> — usuario `admin`, clave `nifi12345678` |
| PostgreSQL (desde NiFi) | `jdbc:postgresql://postgres:5432/demo` — usuario `nifi`, clave `nifi123` |
| PostgreSQL (desde tu PC, p. ej. DataGrip) | host `localhost`, puerto `15432`, BD `demo`, usuario `nifi`, clave `nifi123` |
| **Página de la demo** (subir CSV y ver la tabla en vivo) | <http://localhost:18000> |
| Adminer (ver la BD en el navegador) | <http://localhost:18080> — Sistema `PostgreSQL`, servidor `postgres`, usuario `nifi`, clave `nifi123`, BD `demo` |

> NiFi 2.x solo funciona por **HTTPS**. El navegador avisará que el certificado no es seguro: es normal, pulsa *Avanzado → Continuar*.

> Las credenciales son de prueba y están escritas en el repositorio a propósito. No uses esta configuración fuera de una demo local.

### Cambios respecto a la especificación original

| Especificación | En este proyecto | Motivo |
|---|---|---|
| NiFi en el puerto `8080` (HTTP) | `8443` (HTTPS) con usuario y clave | NiFi 2.x ya no ofrece HTTP; solo HTTPS con inicio de sesión |
| PostgreSQL en el puerto `5432` | `15432` en el host (`5432` dentro de Docker) | Evitar choques con un PostgreSQL ya instalado en la PC |
| `GetFile` lee de `/opt/nifi/nifi-current/data` | Lee de `.../data/entrada` | Separar la entrada de la carpeta `errores` |
| — | Driver JDBC en `drivers/` | NiFi no incluye el driver de PostgreSQL |
| — | Página web, PostgREST y Adminer | Extras para que la demo sea visual |

---

## 1. Antes de la clase (preparación)

Requisito: Docker Desktop abierto.

```powershell
docker compose down     # empezar limpio (borra flujo y datos anteriores)
docker compose up -d
```

NiFi tarda **1–2 minutos** en arrancar. Cuando `https://localhost:8443/nifi` muestre la pantalla de login, ejecuta `python crear_flujo.py` si vas a usar la versión rápida del guion.

**Recomendación:** levántalo 10 minutos antes de empezar y deja abiertas las pestañas de NiFi y de la página (<http://localhost:18000>).

---

## 2. Guion sugerido (≈ 30 min)

**Versión rápida (flujo creado con `crear_flujo.py` antes de entrar a clase):**

| Min | Bloque |
|---|---|
| 0–7 | Teoría: qué es NiFi, ETL, FlowFile, Processor, Connection, Controller Service |
| 7–12 | Recorrer el flujo ya armado: abrir **Configure** de cada caja y mostrar 2–3 propiedades clave |
| 12–17 | Demo automática: copiar `datos.csv` a `data\entrada` y ver la tabla llenarse |
| 17–22 | Los compañeros envían CSVs desde su celular (`http://<IP>:18000`) |
| 22–25 | Error en vivo: `datos_con_error.csv` → `data\errores` |
| 25–30 | Preguntas |

**Versión completa (armando el flujo a mano):**

| Min | Bloque |
|---|---|
| 0–8 | Teoría: qué es NiFi, ETL, FlowFile, Processor, Connection, Controller Service |
| 8–23 | Demo en vivo: construir el flujo (sección 3) |
| 23–27 | Manejo de errores y transformación (secciones 4 y 5) |
| 27–30 | Preguntas |

Al explicar el vocabulario, conéctalo con lo que verán:

- **FlowFile** = el `datos.csv` viajando por el flujo (contenido + atributos como `filename`).
- **Processor** = cada caja (`GetFile`, `PutDatabaseRecord`).
- **Connection** = cada flecha; es una **cola** y muestra cuántos FlowFiles esperan.
- **Controller Service** = recursos compartidos: el lector de CSV y el pool de conexiones a la BD.

---

## 3. Demo paso a paso

### Paso 1 — Controller Services (conexión a la BD y lector CSV)

1. Clic derecho en el lienzo vacío → **Controller Services** → botón **+**.
2. Añade **DBCPConnectionPool** y configúralo (menú ⋮ → *Edit*):

   | Propiedad | Valor |
   |---|---|
   | Database Connection URL | `jdbc:postgresql://postgres:5432/demo` |
   | Database Driver Class Name | `org.postgresql.Driver` |
   | Database Driver Locations | `/opt/nifi/nifi-current/drivers/postgresql-42.7.14.jar` |
   | Database User | `nifi` |
   | Password | `nifi123` |

3. Añade **CSVReader** y configúralo:

   | Propiedad | Valor |
   |---|---|
   | Treat First Line as Header | `true` |
   | Date Format | `yyyy-MM-dd` |

4. Habilita ambos servicios (menú ⋮ → **Enable**).

> Punto para explicar: la URL usa `postgres` (nombre del contenedor), no `localhost`, porque NiFi y PostgreSQL se ven por la red interna de Docker.

### Paso 2 — Extraer: `GetFile`

1. Arrastra el icono **Processor** de la barra superior al lienzo y busca **GetFile**.
2. Configure → **Properties**:

   | Propiedad | Valor |
   |---|---|
   | Input Directory | `/opt/nifi/nifi-current/data/entrada` |
   | File Filter | `.*\.csv` |

3. Pestaña **Scheduling** → **Run Schedule** = `1 sec`. Con el valor por defecto (`0 sec`) revisa la carpeta sin pausa y consume mucha CPU.

> `GetFile` **borra** el archivo después de leerlo (`Keep Source File = false`). Por eso los originales están en `muestras/`.

### Paso 3 — Cargar: `PutDatabaseRecord`

1. Añade un procesador **PutDatabaseRecord**.
2. Properties:

   | Propiedad | Valor |
   |---|---|
   | Record Reader | `CSVReader` |
   | Database Type | `PostgreSQL` |
   | Statement Type | `INSERT` |
   | Database Connection Pooling Service | `DBCPConnectionPool` |
   | Table Name | `clientes` |

3. Pestaña **Relationships**: marca *terminate* en `success` y `retry`.
4. Conecta `GetFile` → `PutDatabaseRecord` (arrastra la flecha desde el centro de GetFile) con la relación `success`.

> No hace falta mapear columnas: NiFi empareja los encabezados del CSV con las columnas de la tabla. El `id` lo genera PostgreSQL (`SERIAL`).

### Paso 4 — Errores: `PutFile`

1. Añade un procesador **PutFile** con `Directory` = `/opt/nifi/nifi-current/data/errores`.
2. En Relationships marca *terminate* en `success` y `failure`.
3. Conecta `PutDatabaseRecord` → `PutFile` con la relación **`failure`**.

Ahora todas las cajas deberían tener el icono de ■ (detenido) y **ningún triángulo amarillo** de advertencia.

### Paso 5 — Ejecutar

1. Clic derecho en el lienzo → **Start**.
2. En el Explorador de Windows, copia `muestras\datos.csv` a `data\entrada\`.
3. En unos segundos el archivo desaparece de `entrada` y los contadores *In / Out* de los procesadores cambian. Refresca el lienzo si no lo ves.

### Paso 6 — Verificar en la base de datos

```powershell
docker exec -it postgres psql -U nifi -d demo -c "SELECT * FROM clientes;"
```

Deben aparecer los 5 clientes, con tildes y fechas correctas.

**Versión visual:** abre Adminer en <http://localhost:18080>, entra y haz clic en **registros clientes** (menú izquierdo). Recarga (F5) después de cada CSV para ver las filas nuevas.

**Linaje (para lucirse):** clic derecho en `PutDatabaseRecord` → **View Data Provenance**. Abre un evento y muestra los atributos y el contenido del FlowFile: NiFi registra de dónde vino cada dato.

---

## 4. Manejo de errores en vivo

Copia `muestras\datos_con_error.csv` a `data\entrada\`.

- La BD rechaza `no-es-una-fecha` y el archivo aparece en **`data\errores\`**.
- En la esquina de `PutDatabaseRecord` aparece un cuadro rojo (*bulletin*) con el error de PostgreSQL.
- La tabla sigue con 5 filas: **los datos malos no contaminan la BD**.

Pregunta de debate: *¿y si en vez de mover el archivo quisiéramos avisar por correo?* → conectar `failure` a un **PutEmail**.

## 5. Transformación con `UpdateRecord`

Copia `muestras\datos_fecha_latina.csv` a `data\entrada\`: falla y va a `errores`, porque `15/06/2026` no es una fecha válida para PostgreSQL. Lo arreglamos con una transformación:

1. Detén el flujo (clic derecho en el lienzo → **Stop**) y borra la flecha `GetFile → PutDatabaseRecord`.
2. Crea dos Controller Services nuevos: otro **CSVReader** (solo `Treat First Line as Header = true`, **sin** Date Format) y un **CSVRecordSetWriter** (valores por defecto). Habilítalos.
3. Añade un procesador **UpdateRecord**:
   - Record Reader = el CSVReader nuevo, Record Writer = `CSVRecordSetWriter`.
   - Replacement Value Strategy = `Literal Value`.
   - Pulsa **+** para añadir una propiedad dinámica:
     - Nombre: `/fecha_registro`
     - Valor:
       ```
       ${field.value:contains('/'):ifElse(${field.value:toDate('dd/MM/yyyy'):format('yyyy-MM-dd')}, ${field.value})}
       ```
4. Conecta `GetFile → UpdateRecord` (`success`), `UpdateRecord → PutDatabaseRecord` (`success`) y `UpdateRecord → PutFile` (`failure`).
5. **Start** y vuelve a copiar `datos_fecha_latina.csv` a `entrada`. Ahora Elena y Jorge entran con fechas `2026-06-15` y `2026-07-02`.

> La expresión dice: *"si la fecha tiene `/`, conviértela de `dd/MM/yyyy` a `yyyy-MM-dd`; si no, déjala igual"*. Así los CSV con fechas ISO siguen funcionando.

---

## 5b. Página web de la demo

<http://localhost:18000> es una página para que el público **vea** el recorrido del archivo:

- A la izquierda eliges un CSV (arrastrándolo o con los botones de ejemplo) y pulsas **Enviar a NiFi**.
- Arriba, el diagrama se ilumina paso a paso: página → NiFi → PostgreSQL. Se pone en rojo si los datos fallan.
- A la derecha está la tabla `clientes` en vivo. Las filas nuevas parpadean en amarillo. El botón **Vaciar tabla** sirve para repetir la demo.

Para que funcione, el flujo necesita un procesador más:

1. Añade un procesador **ListenHTTP** con `Listening Port` = `9090` y `Base Path` = `subir`.
2. Conéctalo a `PutDatabaseRecord` con la relación `success`.

`crear_flujo.py` ya lo incluye. Así NiFi tiene **dos entradas**, la carpeta y la web, que comparten el mismo proceso de carga: buen ejemplo de reutilización.

Cómo está armada: la página la sirve **nginx**, que reenvía `/subir` a NiFi y `/api/` a **PostgREST**. PostgREST es una pequeña API que lee la tabla.

## 6. Plan B: crear el flujo automáticamente

Si algo falla en vivo, con el entorno recién levantado ejecuta:

```powershell
python crear_flujo.py
```

Crea y arranca los Controller Services y los procesadores de la sección 3 (sin el `UpdateRecord`). Solo usa la librería estándar de Python.

Si el lienzo ya tiene algo, el script **no hace nada**, para no duplicar el flujo. Para borrar lo que haya y crearlo limpio:

```powershell
python crear_flujo.py --reiniciar
```

## 6b. Para los compañeros

### Opción A — Durante la clase, desde su celular o laptop (sin instalar nada)

Todos deben estar en la **misma red Wi-Fi** que la PC del expositor.

1. El expositor busca su IP con `ipconfig` (línea *Dirección IPv4* del adaptador Wi-Fi, p. ej. `10.58.23.81`).
2. Los compañeros abren `http://<esa-IP>:18000` y suben CSVs. Todos ven la misma tabla, y el expositor proyecta NiFi procesando lo que ellos envían.

Si no les carga, el firewall de Windows está bloqueando el puerto. Ábrelo una vez en PowerShell **como administrador**:

```powershell
New-NetFirewallRule -DisplayName "Demo NiFi 18000" -Direction Inbound -Protocol TCP -LocalPort 18000 -Action Allow
```

Y bórralo después de la clase:

```powershell
Remove-NetFirewallRule -DisplayName "Demo NiFi 18000"
```

> Algunas redes de universidad aíslan los equipos entre sí. En ese caso, crea un hotspot desde tu celular y conecta a todos ahí.

### Opción B — En su propia computadora

Requisitos: **Docker Desktop**, **Python 3** y unos **4 GB libres** en disco.

1. Copiar esta carpeta completa (zip o repositorio). El driver JDBC ya viene en `drivers/`.
2. En una terminal dentro de la carpeta:
   ```powershell
   docker compose up -d
   ```
3. Esperar 1–2 minutos y ejecutar:
   ```powershell
   python crear_flujo.py
   ```
4. Abrir <http://localhost:18000>, o seguir la sección 3 para armar el flujo a mano en <https://localhost:8443/nifi>.

## 7. Reiniciar desde cero (entre ensayos)

**Solo la tabla:** botón **Vaciar tabla** de la página. Borra las filas y los `id` vuelven a empezar en 1; el flujo de NiFi no se toca.

**Todo (flujo de NiFi + base de datos):**

```powershell
docker compose down
docker compose up -d
python crear_flujo.py      # tras 1–2 minutos, si no vas a armar el flujo a mano
```

Los contenedores no guardan volúmenes, así que esto borra el flujo de NiFi y vacía la tabla. Ideal para ensayar varias veces.

**Archivos con error:** NiFi los deja en `data\errores\`. Bórralos desde el Explorador o con:

```powershell
Get-ChildItem data\errores -Exclude .gitkeep | Remove-Item
```

Los que llegan desde la página tienen un nombre tipo UUID sin extensión; se abren con el Bloc de notas.

**Apagar sin perder nada:** `docker compose stop` (y luego `docker compose start`).

## 8. Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `localhost:8443` no carga | NiFi sigue arrancando; espera 1–2 min. Revisa con `docker logs nifi`. |
| `port is already allocated` | Otro programa usa el puerto. Cambia el puerto izquierdo en `docker-compose.yml` (p. ej. `"15433:5432"`). |
| Triángulo amarillo en un procesador | Pasa el ratón por encima: suele ser una relación sin conectar ni *terminate*, o un servicio sin habilitar. |
| El CSV no desaparece de `entrada` | El flujo no está iniciado (Start) o el archivo no termina en `.csv`. En Windows puede tardar 15–20 s en detectarlo. |
| La página dice "NiFi no recibió el archivo" | Falta el flujo: ejecuta `python crear_flujo.py`. |
| Hay cajas duplicadas o `▶ 8` en la barra de NiFi | Se ejecutó `crear_flujo.py` dos veces: `python crear_flujo.py --reiniciar`. |
| NiFi se apaga solo al arrancar | Falta espacio en disco; Docker necesita varios GB libres. |
