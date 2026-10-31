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
| `data/entrada/` | Carpeta que NiFi vigila (el CSV) |
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

> NiFi 2.x solo funciona por **HTTPS**. El navegador avisará que el certificado no es seguro

Requisito: Docker Desktop abierto.

```powershell
docker compose down     # empezar limpio (borra flujo y datos anteriores)
docker compose up -d
```

- **FlowFile** = el `datos.csv` viajando por el flujo (contenido + atributos como `filename`).
- **Processor** = cada caja (`GetFile`, `PutDatabaseRecord`).
- **Connection** = cada flecha; es una **cola** y muestra cuántos FlowFiles esperan.
- **Controller Service** = recursos compartidos: el lector de CSV y el pool de conexiones a la BD.


## Manejo de errores en vivo

Copiar `muestras\datos_con_error.csv` a `data\entrada\`.

- La BD rechaza `no-es-una-fecha` y el archivo aparece en **`data\errores\`**.
- En la esquina de `PutDatabaseRecord` aparece un cuadro rojo (*bulletin*) con el error de PostgreSQL.
- La tabla sigue con 5 filas: **los datos malos no contaminan la BD**.

SI QUEREMOS QUE MANDE EL AVISO DE ERROR POR CORREO conectar `failure` a un **PutEmail**.

Para que funcione, el flujo necesita un procesador más:

1. Añade un procesador **ListenHTTP** con `Listening Port` = `9090` y `Base Path` = `subir`.
2. Conéctalo a `PutDatabaseRecord` con la relación `success`.

`crear_flujo.py` ya lo incluye. Así NiFi tiene **dos entradas**, la carpeta y la web, que comparten el mismo proceso de carga: buen ejemplo de reutilización.

Cómo está armada: la página la sirve **nginx**, que reenvía `/subir` a NiFi y `/api/` a **PostgREST**. PostgREST es una pequeña API que lee la tabla.


## Reiniciar desde cero

**Solo la tabla:** botón **Vaciar tabla** de la página. Borra las filas y los `id` vuelven a empezar en 1; el flujo de NiFi no se toca.

**Todo (flujo de NiFi + base de datos):**

```powershell
docker compose down
docker compose up -d
python crear_flujo.py      # tras 1–2 minutos, si no vas a armar el flujo a mano
```

Los contenedores no guardan volúmenes, así que esto borra el flujo de NiFi y vacía la tabla. 

**Archivos con error:** NiFi los deja en `data\errores\`. Bórralos desde el Explorador o con:

```powershell
Get-ChildItem data\errores -Exclude .gitkeep | Remove-Item
```

Los que llegan desde la página tienen un nombre tipo UUID sin extensión; se abren con el Bloc de notas.

**Apagar sin perder nada:** `docker compose stop` (y luego `docker compose start`).

## Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `localhost:8443` no carga | NiFi sigue arrancando; espera 1–2 min. Revisa con `docker logs nifi`. |
| `port is already allocated` | Otro programa usa el puerto. Cambia el puerto izquierdo en `docker-compose.yml` (p. ej. `"15433:5432"`). |
| Triángulo amarillo en un procesador | Pasa el ratón por encima: suele ser una relación sin conectar ni *terminate*, o un servicio sin habilitar. |
| El CSV no desaparece de `entrada` | El flujo no está iniciado (Start) o el archivo no termina en `.csv`. En Windows puede tardar 15–20 s en detectarlo. |
| La página dice "NiFi no recibió el archivo" | Falta el flujo: ejecuta `python crear_flujo.py`. |
| Hay cajas duplicadas o `▶ 8` en la barra de NiFi | Se ejecutó `crear_flujo.py` dos veces: `python crear_flujo.py --reiniciar`. |
| NiFi se apaga solo al arrancar | Falta espacio en disco; Docker necesita varios GB libres. |
