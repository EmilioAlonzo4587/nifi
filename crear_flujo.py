"""Plan B: crea automáticamente el flujo CSV -> PostgreSQL en NiFi usando su API REST.

Uso:  python crear_flujo.py              crea el flujo (si el lienzo está vacío)
      python crear_flujo.py --reiniciar  borra todo lo que haya en el lienzo y lo vuelve a crear
Requiere que `docker compose up -d` ya esté corriendo. Solo usa la librería estándar.
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://localhost:8443/nifi-api"
USUARIO, CLAVE = "admin", "nifi12345678"
CTX = ssl._create_unverified_context()  # NiFi usa un certificado autofirmado
TOKEN = None


def api(metodo, ruta, cuerpo=None):
    datos = None
    cabeceras = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode()
        cabeceras["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + ruta, data=datos, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, context=CTX) as r:
            texto = r.read().decode()
            return json.loads(texto) if texto.startswith("{") else texto
    except urllib.error.HTTPError as e:
        sys.exit(f"Error {e.code} en {metodo} {ruta}: {e.read().decode()}")


def login():
    global TOKEN
    datos = urllib.parse.urlencode({"username": USUARIO, "password": CLAVE}).encode()
    req = urllib.request.Request(BASE + "/access/token", data=datos, method="POST")
    with urllib.request.urlopen(req, context=CTX) as r:
        TOKEN = r.read().decode()


def propiedades(descriptores, por_nombre_visible):
    """Traduce nombres visibles en la UI ('Table Name') al nombre interno de la propiedad."""
    mapa = {d["displayName"]: d["name"] for d in descriptores.values()}
    return {mapa[k]: v for k, v in por_nombre_visible.items()}


def crear_servicio(pg, tipo, props):
    s = api("POST", f"/process-groups/{pg}/controller-services",
            {"revision": {"version": 0}, "component": {"type": tipo}})
    comp = s["component"]
    s = api("PUT", f"/controller-services/{comp['id']}", {
        "revision": s["revision"],
        "component": {"id": comp["id"], "properties": propiedades(comp["descriptors"], props)},
    })
    api("PUT", f"/controller-services/{comp['id']}/run-status",
        {"revision": s["revision"], "state": "ENABLED"})
    return comp["id"]


def crear_procesador(pg, tipo, nombre, x, y, props, auto_terminar, cada="0 sec"):
    p = api("POST", f"/process-groups/{pg}/processors", {
        "revision": {"version": 0},
        "component": {"type": tipo, "name": nombre, "position": {"x": x, "y": y}},
    })
    comp = p["component"]
    api("PUT", f"/processors/{comp['id']}", {
        "revision": p["revision"],
        "component": {"id": comp["id"], "config": {
            "properties": propiedades(comp["config"]["descriptors"], props),
            "autoTerminatedRelationships": auto_terminar,
            "schedulingPeriod": cada,  # cada cuánto se ejecuta (Scheduling > Run Schedule)
        }},
    })
    return comp["id"]


def vaciar_lienzo(pg):
    """Detiene y borra todos los procesadores, conexiones y servicios del grupo raíz."""
    api("PUT", f"/flow/process-groups/{pg}", {"id": pg, "state": "STOPPED"})
    time.sleep(2)
    flujo = api("GET", f"/flow/process-groups/{pg}")["processGroupFlow"]["flow"]
    for cn in flujo["connections"]:
        api("POST", f"/flowfile-queues/{cn['id']}/drop-requests")  # vaciar la cola
        api("DELETE", f"/connections/{cn['id']}?version={cn['revision']['version']}")
    for p in flujo["processors"]:
        api("DELETE", f"/processors/{p['id']}?version={p['revision']['version']}")
    for s in api("GET", f"/flow/process-groups/{pg}/controller-services")["controllerServices"]:
        s = api("PUT", f"/controller-services/{s['id']}/run-status",
                {"revision": s["revision"], "state": "DISABLED"})
        time.sleep(1)
        s = api("GET", f"/controller-services/{s['id']}")
        api("DELETE", f"/controller-services/{s['id']}?version={s['revision']['version']}")


def conectar(pg, origen, destino, relaciones):
    api("POST", f"/process-groups/{pg}/connections", {
        "revision": {"version": 0},
        "component": {
            "source": {"id": origen, "groupId": pg, "type": "PROCESSOR"},
            "destination": {"id": destino, "groupId": pg, "type": "PROCESSOR"},
            "selectedRelationships": relaciones,
        },
    })


def main():
    login()
    raiz = api("GET", "/flow/process-groups/root")["processGroupFlow"]
    pg = raiz["id"]
    if raiz["flow"]["processors"]:
        if "--reiniciar" not in sys.argv:
            sys.exit("El lienzo de NiFi ya tiene un flujo; no se crea otro para no duplicarlo.\n"
                     "Para borrarlo y crearlo de nuevo: python crear_flujo.py --reiniciar")
        print("Borrando el flujo existente...")
        vaciar_lienzo(pg)

    dbcp = crear_servicio(pg, "org.apache.nifi.dbcp.DBCPConnectionPool", {
        "Database Connection URL": "jdbc:postgresql://postgres:5432/demo",
        "Database Driver Class Name": "org.postgresql.Driver",
        "Database Driver Locations": "/opt/nifi/nifi-current/drivers/postgresql-42.7.14.jar",
        "Database User": "nifi",
        "Password": "nifi123",
    })
    lector = crear_servicio(pg, "org.apache.nifi.csv.CSVReader", {
        "Treat First Line as Header": "true",
        "Date Format": "yyyy-MM-dd",
    })

    get_file = crear_procesador(pg, "org.apache.nifi.processors.standard.GetFile", "Leer CSV", 0, 0, {
        "Input Directory": "/opt/nifi/nifi-current/data/entrada",
        "File Filter": r".*\.csv",
    }, [], cada="1 sec")  # sin pausa revisaría la carpeta millones de veces y gastaría CPU
    put_db = crear_procesador(pg, "org.apache.nifi.processors.standard.PutDatabaseRecord",
                              "Insertar en PostgreSQL", 0, 250, {
        "Record Reader": lector,
        "Database Type": "PostgreSQL",
        "Statement Type": "INSERT",
        "Database Connection Pooling Service": dbcp,
        "Table Name": "clientes",
    }, ["success", "retry"])
    put_file = crear_procesador(pg, "org.apache.nifi.processors.standard.PutFile",
                                "Mover a errores", 500, 250, {
        "Directory": "/opt/nifi/nifi-current/data/errores",
    }, ["success", "failure"])

    # Entrada alternativa: la página web (http://localhost:18000) envía el CSV por HTTP
    listen = crear_procesador(pg, "org.apache.nifi.processors.standard.ListenHTTP",
                              "Recibir CSV desde la web", 500, 0, {
        "Listening Port": "9090",
        "Base Path": "subir",
    }, [])

    conectar(pg, get_file, put_db, ["success"])
    conectar(pg, listen, put_db, ["success"])
    conectar(pg, put_db, put_file, ["failure"])

    time.sleep(1)
    api("PUT", f"/flow/process-groups/{pg}", {"id": pg, "state": "RUNNING"})
    print("Flujo creado e iniciado. Copia un CSV de muestras/ a data/entrada/ para dispararlo.")


if __name__ == "__main__":
    main()
