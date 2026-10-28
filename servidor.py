from flask import Flask, render_template, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    Jsonb = None
import os
import time
import threading
import uuid
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from io import BytesIO


from riot_api import (
    jugador_en_partida,
    obtener_puuid_por_riot_id,
    registrar_cuenta_riot,
    actualizar_partidas_jugador,
    obtener_rango,
    obtener_ultimo_codigo_http
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

app = Flask(__name__)

CORS(
    app,
    origins=[
        "https://soloqchallenge-monteros.netlify.app"
    ]
)

# PostgreSQL en Render.
# Si DATABASE_URL no existe, se permite trabajar localmente con datos.json.
DATABASE_URL = os.environ.get("DATABASE_URL")
ARCHIVO = "datos.json"
COMPROBANTES_DIR = "comprobantes"
MAX_COMPROBANTE_BYTES = 5 * 1024 * 1024

# Actualización de historial + ranking cada 10 minutos
INTERVALO_ACTUALIZACION = 10 * 60

# Estado de partida: máximo 1 consulta cada 15 segundos
# por jugador
INTERVALO_ESTADO = 15

# Cuando Riot devuelve 429, esperamos 60 segundos
# antes de volver a consultar.
PAUSA_RATE_LIMIT = 60

# Torneo: del 5 al 30 de noviembre de 2026, 100 horas totales.
HORAS_MAXIMAS_TORNEO = 100
SEGUNDOS_MAXIMOS_TORNEO = HORAS_MAXIMAS_TORNEO * 3600
LATIDO_MAXIMO_SEGUNDOS = 45
FECHA_INICIO_TORNEO = "2026-11-05"
FECHA_FIN_TORNEO = "2026-11-30"
ZONA_TORNEO = ZoneInfo("America/Argentina/Buenos_Aires")

def torneo_en_fecha():
    hoy = datetime.now(ZONA_TORNEO).date().isoformat()
    return FECHA_INICIO_TORNEO <= hoy <= FECHA_FIN_TORNEO


def inicializar_control_tiempo(jugador):
    jugador.setdefault("segundos_torneo", 0)
    jugador.setdefault("agente_token", secrets.token_urlsafe(32))
    jugador.setdefault("agente_ultimo_latido", None)
    jugador.setdefault("agente_sesion_activa", False)
    jugador.setdefault("agente_ultima_actividad", None)
    jugador.setdefault("completado", False)
    jugador.setdefault("completado_en", None)
    jugador.setdefault("estadisticas_finales", None)
    try:
        jugador["segundos_torneo"] = max(0, min(SEGUNDOS_MAXIMOS_TORNEO, int(jugador.get("segundos_torneo", 0))))
    except (TypeError, ValueError):
        jugador["segundos_torneo"] = 0
    return jugador


def finalizar_jugador_si_corresponde(nombre, jugador):
    inicializar_control_tiempo(jugador)
    if jugador.get("segundos_torneo", 0) >= SEGUNDOS_MAXIMOS_TORNEO and not jugador.get("estadisticas_finales"):
        jugador["segundos_torneo"] = SEGUNDOS_MAXIMOS_TORNEO
        jugador["completado"] = True
        jugador["completado_en"] = jugador.get("completado_en") or datetime.now(timezone.utc).isoformat()
        jugador["agente_sesion_activa"] = False
        jugador["estadisticas_finales"] = {
            "rango": jugador.get("rango"),
            "partidas_riot": (jugador.get("partidas_riot") or [])[:5],
            "ultima_partida": jugador.get("ultima_partida"),
            "fecha": jugador["completado_en"]
        }
        print(f"{nombre}: completó las 100 horas del torneo.")


def tiempo_torneo(jugador):
    inicializar_control_tiempo(jugador)
    segundos = min(SEGUNDOS_MAXIMOS_TORNEO, int(jugador.get("segundos_torneo", 0)))
    return {
        "segundos_torneo": segundos,
        "horas_jugadas": round(segundos / 3600, 2),
        "horas_restantes": round(max(0, SEGUNDOS_MAXIMOS_TORNEO - segundos) / 3600, 2),
        "completado": bool(jugador.get("completado")),
        "completado_en": jugador.get("completado_en")
    }


# ============================================================
# VARIABLES GLOBALES
# ============================================================

ultima_actualizacion = 0

bloqueo_actualizacion = threading.Lock()

# ------------------------------------------------------------
# Estado de jugadores
# ------------------------------------------------------------

cache_estados = {}

# Guarda cuándo se hizo la última consulta REAL a Riot
ultima_consulta_estado = {}

bloqueo_estados = threading.Lock()

# ------------------------------------------------------------
# Control de actualización de Riot
# ------------------------------------------------------------

# Índice del jugador donde debemos continuar después
# de un Rate Limit.
indice_proximo_jugador = 0

# Momento hasta el cual debemos esperar después de un 429.
pausa_hasta = 0


# ============================================================
# BASE DE DATOS
# ============================================================

def inicializar_base_datos():

    if not DATABASE_URL:

        print("DATABASE_URL no configurada. Se utilizará datos.json localmente.")
        return

    if psycopg is None:

        raise RuntimeError(
            "Falta el paquete psycopg. Revisá requirements.txt."
        )

    try:

        with psycopg.connect(DATABASE_URL) as conexion:

            conexion.execute("""
                CREATE TABLE IF NOT EXISTS app_data (
                    id INTEGER PRIMARY KEY,
                    datos JSONB NOT NULL
                )
            """)

            conexion.execute("""
                CREATE TABLE IF NOT EXISTS comprobantes_registro (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL,
                    archivo BYTEA NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conexion.execute("""
                CREATE TABLE IF NOT EXISTS consultas_registro (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    consulta TEXT NOT NULL,
                    creada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acceso_token TEXT UNIQUE
                )
            """)

            conexion.execute("""
                ALTER TABLE consultas_registro
                ADD COLUMN IF NOT EXISTS acceso_token TEXT UNIQUE
            """)

            conexion.execute("""
                CREATE TABLE IF NOT EXISTS consultas_mensajes (
                    id SERIAL PRIMARY KEY,
                    consulta_id INTEGER NOT NULL REFERENCES consultas_registro(id) ON DELETE CASCADE,
                    autor_tipo TEXT NOT NULL,
                    autor_nombre TEXT NOT NULL,
                    mensaje TEXT NOT NULL,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        os.makedirs(COMPROBANTES_DIR, exist_ok=True)

        print("PostgreSQL conectado correctamente.")

    except Exception as e:

        print("ERROR AL INICIALIZAR POSTGRESQL:", e)
        raise



def guardar_comprobante(nombre, contenido, mime_type, extension):

    if DATABASE_URL:

        with psycopg.connect(DATABASE_URL) as conexion:

            fila = conexion.execute(
                """
                INSERT INTO comprobantes_registro (nombre, mime_type, archivo)
                VALUES (%s, %s, %s)
                ON CONFLICT (nombre) DO UPDATE SET
                    mime_type = EXCLUDED.mime_type,
                    archivo = EXCLUDED.archivo,
                    creado_en = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (nombre, mime_type, contenido)
            ).fetchone()

        return {"tipo": "postgres", "id": fila[0]}

    os.makedirs(COMPROBANTES_DIR, exist_ok=True)
    nombre_archivo = f"{uuid.uuid4().hex}.{extension}"
    ruta = os.path.join(COMPROBANTES_DIR, nombre_archivo)

    with open(ruta, "wb") as archivo:
        archivo.write(contenido)

    return {"tipo": "local", "archivo": nombre_archivo}


def obtener_comprobante(referencia):

    if not referencia:
        return None

    if isinstance(referencia, dict) and referencia.get("tipo") == "postgres":

        if not DATABASE_URL:
            return None

        with psycopg.connect(DATABASE_URL) as conexion:
            return conexion.execute(
                "SELECT mime_type, archivo FROM comprobantes_registro WHERE id = %s",
                (referencia.get("id"),)
            ).fetchone()

    if isinstance(referencia, dict) and referencia.get("tipo") == "local":

        nombre_archivo = os.path.basename(str(referencia.get("archivo", "")))
        ruta = os.path.join(COMPROBANTES_DIR, nombre_archivo)

        if not os.path.exists(ruta):
            return None

        mime_type = "image/png" if nombre_archivo.lower().endswith(".png") else "image/jpeg"
        return mime_type, ruta

    return None


def eliminar_comprobante(referencia):

    if not referencia:
        return

    try:

        if isinstance(referencia, dict) and referencia.get("tipo") == "postgres":

            if DATABASE_URL:
                with psycopg.connect(DATABASE_URL) as conexion:
                    conexion.execute(
                        "DELETE FROM comprobantes_registro WHERE id = %s",
                        (referencia.get("id"),)
                    )

            return

        if isinstance(referencia, dict) and referencia.get("tipo") == "local":

            nombre_archivo = os.path.basename(str(referencia.get("archivo", "")))
            ruta = os.path.join(COMPROBANTES_DIR, nombre_archivo)

            if os.path.exists(ruta):
                os.remove(ruta)

    except Exception as e:
        print("ERROR AL ELIMINAR COMPROBANTE:", e)


def cargar_datos():

    # --------------------------------------------------------
    # RENDER / POSTGRESQL
    # --------------------------------------------------------

    if DATABASE_URL:

        try:

            with psycopg.connect(DATABASE_URL) as conexion:

                fila = conexion.execute(
                    "SELECT datos FROM app_data WHERE id = 1"
                ).fetchone()

            if not fila:

                return {
                    "jugadores": {},
                    "solicitudes_registro": []
                }

            datos = fila[0]

            if not isinstance(datos, dict):

                return {
                    "jugadores": {},
                    "solicitudes_registro": []
                }

            if not isinstance(datos.get("jugadores"), dict):

                datos["jugadores"] = {}

            if not isinstance(datos.get("solicitudes_registro"), list):

                datos["solicitudes_registro"] = []

            return datos

        except Exception as e:

            print("ERROR AL CARGAR DATOS DESDE POSTGRESQL:", e)
            raise


    # --------------------------------------------------------
    # DESARROLLO LOCAL SIN DATABASE_URL
    # --------------------------------------------------------

    try:

        if not os.path.exists(ARCHIVO):

            return {
                "jugadores": {},
                "solicitudes_registro": []
            }

        import json

        with open(
            ARCHIVO,
            "r",
            encoding="utf-8"
        ) as archivo:

            datos = json.load(archivo)

        if not isinstance(datos, dict):

            return {
                "jugadores": {},
                "solicitudes_registro": []
            }

        if not isinstance(datos.get("jugadores"), dict):

            datos["jugadores"] = {}

        if not isinstance(datos.get("solicitudes_registro"), list):

            datos["solicitudes_registro"] = []

        return datos

    except Exception as e:

        print("ERROR AL CARGAR DATOS LOCALES:", e)

        return {
            "jugadores": {},
            "solicitudes_registro": []
        }


def guardar_datos(datos):

    # --------------------------------------------------------
    # RENDER / POSTGRESQL
    # --------------------------------------------------------

    if DATABASE_URL:

        try:

            with psycopg.connect(DATABASE_URL) as conexion:

                conexion.execute(
                    """
                    INSERT INTO app_data (id, datos)
                    VALUES (1, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET datos = EXCLUDED.datos
                    """,
                    (Jsonb(datos),)
                )

            return

        except Exception as e:

            print("ERROR AL GUARDAR DATOS EN POSTGRESQL:", e)
            raise


    # --------------------------------------------------------
    # DESARROLLO LOCAL SIN DATABASE_URL
    # --------------------------------------------------------

    try:

        import json

        with open(
            ARCHIVO,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                datos,
                archivo,
                ensure_ascii=False,
                indent=4
            )

    except OSError as e:

        print("ERROR AL GUARDAR DATOS LOCALES:", e)
        raise


# Crear la tabla automáticamente al iniciar el servidor.
inicializar_base_datos()


# ============================================================
# ORDENAR RANKING
# ============================================================

def ordenar_jugadores_ranking(jugadores):

    orden_tier = {

        "IRON": 1,
        "BRONZE": 2,
        "SILVER": 3,
        "GOLD": 4,
        "PLATINUM": 5,
        "EMERALD": 6,
        "DIAMOND": 7,
        "MASTER": 8,
        "GRANDMASTER": 9,
        "CHALLENGER": 10,
        "UNRANKED": 0
    }


    orden_division = {

        "IV": 1,
        "III": 2,
        "II": 3,
        "I": 4
    }


    jugadores_ranking = list(
        jugadores.items()
    )


    jugadores_ranking.sort(

        key=lambda item: (

            orden_tier.get(

                (item[1].get("rango") or {}).get(
                    "tier",
                    "UNRANKED"
                ),

                0
            ),

            orden_division.get(

                (item[1].get("rango") or {}).get(
                    "rank",
                    ""
                ),

                0
            ),

            (item[1].get("rango") or {}).get(
                "lp",
                0
            )
        ),

        reverse=True
    )


    return jugadores_ranking


# ============================================================
# ACTUALIZAR DATOS DE RIOT
# ============================================================

def actualizar_datos_riot():

    global ultima_actualizacion
    global indice_proximo_jugador
    global pausa_hasta


    if not bloqueo_actualizacion.acquire(
        blocking=False
    ):

        return


    try:

        ahora = time.time()


        # ====================================================
        # PAUSA POR RATE LIMIT
        # ====================================================

        if ahora < pausa_hasta:

            segundos = int(
                pausa_hasta - ahora
            )

            print(
                f"Riot en pausa por Rate Limit. "
                f"Reanudando en aproximadamente {segundos}s."
            )

            return


        # ====================================================
        # TODAVÍA NO TOCA ACTUALIZAR
        # ====================================================

        if indice_proximo_jugador == 0:

            if (
                ahora - ultima_actualizacion
                < INTERVALO_ACTUALIZACION
            ):

                return


        print()
        print("===================================")
        print("ACTUALIZANDO DATOS DE RIOT")
        print("===================================")


        datos = cargar_datos()


        jugadores = datos.get(
            "jugadores",
            {}
        )


        lista_jugadores = list(
            jugadores.items()
        )


        total_jugadores = len(
            lista_jugadores
        )


        if total_jugadores == 0:

            ultima_actualizacion = time.time()

            return


        # ====================================================
        # PROTEGER EL ÍNDICE
        # ====================================================

        if indice_proximo_jugador >= total_jugadores:

            indice_proximo_jugador = 0


        # ====================================================
        # RECORRER JUGADORES
        # ====================================================

        for indice in range(
            indice_proximo_jugador,
            total_jugadores
        ):

            nombre, jugador = lista_jugadores[
                indice
            ]

            inicializar_control_tiempo(jugador)
            finalizar_jugador_si_corresponde(nombre, jugador)
            if jugador.get("completado"):
                continue

            print()
            print(
                f"Actualizando: {nombre} "
                f"({indice + 1}/{total_jugadores})"
            )


            # ==================================================
            # 1. OBTENER PUUID
            # ==================================================

            puuid = jugador.get(
                "puuid"
            )


            if not puuid:

                riot_id = jugador.get(
                    "riot_id"
                )

                riot_tag = jugador.get(
                    "riot_tag"
                )


                if not riot_id or not riot_tag:

                    print(
                        "Faltan Riot ID o Riot Tag para:",
                        nombre
                    )

                    continue


                print(
                    "Obteniendo PUUID mediante Riot ID..."
                )


                puuid = obtener_puuid_por_riot_id(
                    riot_id,
                    riot_tag
                )


                codigo = obtener_ultimo_codigo_http()


                if codigo == 429:

                    print(
                        "RATE LIMIT al obtener PUUID."
                    )

                    indice_proximo_jugador = indice

                    pausa_hasta = (
                        time.time()
                        + PAUSA_RATE_LIMIT
                    )

                    print(
                        f"Actualización pausada durante "
                        f"{PAUSA_RATE_LIMIT} segundos."
                    )

                    print(
                        f"Se retomará desde: {nombre}"
                    )

                    return


                if not puuid:

                    print(
                        "No se pudo obtener PUUID para:",
                        nombre
                    )

                    continue


                jugador["puuid"] = puuid


                guardar_datos(
                    datos
                )


                print(
                    "PUUID guardado para:",
                    nombre
                )


            else:

                print(
                    "PUUID ya guardado."
                )


            # ==================================================
            # 2. ACTUALIZAR HISTORIAL
            # ==================================================

            print(
                "Utilizando PUUID para las consultas de Riot."
            )


            try:

                historial_actual = jugador.get(
                    "partidas_riot",
                    []
                )


                if not isinstance(
                    historial_actual,
                    list
                ):

                    historial_actual = []


                # IDs de partidas anteriores
                ids_partidas_anteriores = {

                    partida.get("match_id")

                    for partida in historial_actual

                    if partida.get("match_id")
                }


                partidas = actualizar_partidas_jugador(
                    puuid,
                    historial_actual
                )


                if partidas is not None:

                    jugador["partidas_riot"] = partidas


            except Exception as e:

                print(
                    f"Error actualizando partidas de {nombre}:",
                    e
                )


            codigo = obtener_ultimo_codigo_http()


            if codigo == 429:

                print(
                    "RATE LIMIT al actualizar partidas."
                )

                indice_proximo_jugador = indice

                pausa_hasta = (
                    time.time()
                    + PAUSA_RATE_LIMIT
                )

                print(
                    f"Actualización pausada durante "
                    f"{PAUSA_RATE_LIMIT} segundos."
                )

                print(
                    f"Se retomará desde: {nombre}"
                )

                guardar_datos(
                    datos
                )

                return


            # ==================================================
            # 3. ACTUALIZAR RANGO
            # ==================================================

            try:

                # ------------------------------------------------
                # LP ANTERIOR
                # ------------------------------------------------

                rango_anterior = jugador.get(
                    "rango"
                )


                lp_anterior = None


                if isinstance(
                    rango_anterior,
                    dict
                ):

                    lp_anterior = rango_anterior.get(
                        "lp"
                    )


                # ------------------------------------------------
                # RANGO ACTUAL
                # ------------------------------------------------

                rango = obtener_rango(
                    puuid
                )


                codigo = obtener_ultimo_codigo_http()


                if codigo == 429:

                    print(
                        "RATE LIMIT al obtener rango."
                    )

                    indice_proximo_jugador = indice

                    pausa_hasta = (
                        time.time()
                        + PAUSA_RATE_LIMIT
                    )

                    print(
                        f"Actualización pausada durante "
                        f"{PAUSA_RATE_LIMIT} segundos."
                    )

                    print(
                        f"Se retomará desde: {nombre}"
                    )

                    guardar_datos(
                        datos
                    )

                    return


                if rango:

                    jugador["rango"] = rango


                    lp_nuevo = rango.get(
                        "lp"
                    )


                    print(
                        f"Rango actualizado para {nombre}: "
                        f"{rango.get('tier', '')} "
                        f"{rango.get('rank', '')} "
                        f"{rango.get('lp', 0)} LP"
                    )


                    # =================================================
                    # CALCULAR CAMBIO DE LP
                    # =================================================

                    if (

                        partidas is not None

                        and lp_anterior is not None

                        and lp_nuevo is not None

                    ):

                        nuevas_partidas = [

                            partida

                            for partida in partidas

                            if partida.get("match_id")
                            not in ids_partidas_anteriores
                        ]


                        if nuevas_partidas:

                            cambio_lp = (
                                lp_nuevo
                                - lp_anterior
                            )


                            nuevas_partidas[0][
                                "lp_cambio"
                            ] = cambio_lp


                            print(
                                f"LP cambiado para {nombre}: "
                                f"{cambio_lp:+d} LP"
                            )


            except Exception as e:

                print(
                    f"Error obteniendo rango de {nombre}:",
                    e
                )


            guardar_datos(
                datos
            )


        # ====================================================
        # TODOS LOS JUGADORES TERMINARON
        # ====================================================

        indice_proximo_jugador = 0

        ultima_actualizacion = time.time()


        datos["fecha"] = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        guardar_datos(
            datos
        )


        print()
        print("===================================")
        print("ACTUALIZACIÓN COMPLETA FINALIZADA")
        print("===================================")
        print()


    finally:

        bloqueo_actualizacion.release()


# ============================================================
# OBTENER ESTADO
# ============================================================

def obtener_estado_jugador(
    nombre,
    jugador
):

    global pausa_hasta


    puuid = jugador.get(
        "puuid"
    )


    if not puuid:

        print(
            f"{nombre}: no tiene PUUID guardado."
        )

        return {
            "estado": "offline",
            "game_start_time": None
        }


    ahora = time.time()


    # ========================================================
    # CACHÉ DE 15 SEGUNDOS
    # ========================================================

    with bloqueo_estados:

        estado_anterior = cache_estados.get(
            nombre
        )

        ultima_consulta = ultima_consulta_estado.get(
            nombre,
            0
        )


    if (

        estado_anterior is not None

        and (
            ahora - ultima_consulta
        ) < INTERVALO_ESTADO

    ):

        return estado_anterior


    # ========================================================
    # SI ESTAMOS EN PAUSA POR RATE LIMIT
    # ========================================================

    if ahora < pausa_hasta:

        if estado_anterior:

            return estado_anterior

        return {
            "estado": "offline",
            "game_start_time": None
        }


    try:

        print()
        print(
            f"Consultando estado de {nombre}..."
        )


        # ====================================================
        # ESTA ES LA ÚNICA CONSULTA REAL A SPECTATOR
        # CUANDO EL CACHÉ DE 15 SEGUNDOS EXPIRO
        # ====================================================

        partida = jugador_en_partida(
            puuid
        )


        codigo = obtener_ultimo_codigo_http()


        if codigo == 429:

            print(
                f"{nombre}: RATE LIMIT."
            )


            pausa_hasta = (
                time.time()
                + PAUSA_RATE_LIMIT
            )


            print(
                f"Consultas de estado pausadas "
                f"durante {PAUSA_RATE_LIMIT} segundos."
            )


            if estado_anterior:

                return estado_anterior


            return {
                "estado": "offline",
                "game_start_time": None
            }


        # Registrar el momento de la consulta REAL
        with bloqueo_estados:

            ultima_consulta_estado[nombre] = time.time()


        # ====================================================
        # EN PARTIDA
        # ====================================================

        if partida:

            game_start_time = partida.get(
                "game_start_time"
            )


            estado = {
                "estado": "in_game",
                "game_start_time": game_start_time
            }


            print(
                f"{nombre}: EN PARTIDA."
            )


            with bloqueo_estados:

                cache_estados[nombre] = estado


            return estado


        # ====================================================
        # OFFLINE
        # ====================================================

        estado = {
            "estado": "offline",
            "game_start_time": None
        }


        print(
            f"{nombre}: OFFLINE."
        )


        with bloqueo_estados:

            cache_estados[nombre] = estado


        return estado


    except Exception as e:

        print(
            f"Error obteniendo estado de {nombre}:",
            e
        )


        with bloqueo_estados:

            anterior = cache_estados.get(
                nombre
            )


        if anterior:

            return anterior


        return {
            "estado": "offline",
            "game_start_time": None
        }


# ============================================================
# ACTUALIZAR ESTADOS
# ============================================================

def actualizar_estados():

    datos = cargar_datos()


    jugadores = datos.get(
        "jugadores",
        {}
    )


    for nombre, jugador in jugadores.items():

        inicializar_control_tiempo(jugador)
        if jugador.get("completado"):
            with bloqueo_estados:
                cache_estados[nombre] = {"estado": "completado", "game_start_time": None}
            continue

        estado = obtener_estado_jugador(
            nombre,
            jugador
        )


        with bloqueo_estados:

            cache_estados[nombre] = estado


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/reglas")
def reglas():

    return render_template("reglas.html")


@app.route("/")
def inicio():

    return render_template(
        "index.html"
    )


# ============================================================
# REGISTRO DE JUGADOR
# ============================================================

@app.route("/api/registrar", methods=["POST"])
def registrar_jugador():

    try:

        nombre = str(request.form.get("nombre", "")).strip()
        email = str(request.form.get("email", "")).strip()
        riot_id = str(request.form.get("riot_id", "")).strip()
        riot_tag = str(request.form.get("riot_tag", "")).strip()
        stream_url = str(request.form.get("stream_url", "")).strip()
        comprobante = request.files.get("comprobante")

        if not nombre:
            return jsonify({"ok": False, "error": "Debes ingresar tu nombre."}), 400

        if not email:
            return jsonify({"ok": False, "error": "Debes ingresar tu Gmail."}), 400

        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return jsonify({"ok": False, "error": "Debes ingresar un Gmail válido."}), 400

        if not riot_id:
            return jsonify({"ok": False, "error": "Debes ingresar tu Riot ID."}), 400

        if not riot_tag:
            return jsonify({"ok": False, "error": "Debes ingresar tu Tag."}), 400

        if not comprobante or not comprobante.filename:
            return jsonify({"ok": False, "error": "Debes subir el comprobante de inscripción."}), 400

        extension = comprobante.filename.rsplit(".", 1)[-1].lower() if "." in comprobante.filename else ""
        extensiones_validas = {"jpg", "jpeg", "png"}
        tipos_validos = {"image/jpeg", "image/png"}

        if extension not in extensiones_validas or comprobante.mimetype not in tipos_validos:
            return jsonify({"ok": False, "error": "El comprobante debe ser una imagen JPG, JPEG o PNG."}), 400

        contenido_comprobante = comprobante.read()

        if not contenido_comprobante:
            return jsonify({"ok": False, "error": "El comprobante está vacío."}), 400

        if len(contenido_comprobante) > MAX_COMPROBANTE_BYTES:
            return jsonify({"ok": False, "error": "El comprobante no puede superar los 5 MB."}), 400

        if stream_url and not (stream_url.startswith("http://") or stream_url.startswith("https://")):
            return jsonify({"ok": False, "error": "El link del stream debe comenzar con http:// o https://."}), 400

        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})
        solicitudes = datos.get("solicitudes_registro", [])

        if not isinstance(solicitudes, list):
            solicitudes = []

        if nombre in jugadores:
            return jsonify({"ok": False, "error": "Ese nombre de participante ya está registrado."}), 409

        for solicitud in solicitudes:
            if str(solicitud.get("nombre", "")).strip().lower() == nombre.lower():
                return jsonify({"ok": False, "error": "Ya existe una solicitud pendiente con ese nombre."}), 409

        for nombre_existente, jugador_existente in jugadores.items():
            if (
                str(jugador_existente.get("riot_id", "")).strip().lower() == riot_id.lower()
                and str(jugador_existente.get("riot_tag", "")).strip().lower() == riot_tag.lower()
            ):
                return jsonify({"ok": False, "error": f"Esa cuenta de Riot ya está registrada como {nombre_existente}."}), 409

        for solicitud in solicitudes:
            if (
                str(solicitud.get("riot_id", "")).strip().lower() == riot_id.lower()
                and str(solicitud.get("riot_tag", "")).strip().lower() == riot_tag.lower()
            ):
                return jsonify({"ok": False, "error": "Esa cuenta de Riot ya tiene una solicitud pendiente."}), 409

        print("Nueva solicitud:", nombre, riot_id, riot_tag)

        registro = registrar_cuenta_riot(riot_id, riot_tag)
        codigo = obtener_ultimo_codigo_http()

        if codigo == 429:
            return jsonify({"ok": False, "error": "Riot está limitando temporalmente las consultas. Intenta nuevamente en unos segundos."}), 429

        if not registro or not registro.get("ok"):
            return jsonify({
                "ok": False,
                "error": registro.get("error", "No se pudo validar la cuenta de Riot.") if isinstance(registro, dict) else "No se pudo validar la cuenta de Riot."
            }), 400

        puuid = registro.get("puuid")

        if not puuid:
            return jsonify({"ok": False, "error": "Riot validó la cuenta pero no devolvió el PUUID."}), 500

        referencia_comprobante = guardar_comprobante(
            nombre,
            contenido_comprobante,
            comprobante.mimetype,
            extension
        )

        solicitudes.append({
            "nombre": nombre,
            "email": email,
            "riot_id": riot_id,
            "riot_tag": riot_tag,
            "puuid": puuid,
            "stream_url": stream_url,
            "comprobante": referencia_comprobante,
            "fecha_solicitud": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        try:
            datos["solicitudes_registro"] = solicitudes
            guardar_datos(datos)
        except Exception:
            eliminar_comprobante(referencia_comprobante)
            raise

        return jsonify({
            "ok": True,
            "mensaje": "Solicitud enviada correctamente. Queda pendiente de aprobación.",
            "solicitud": {"nombre": nombre, "riot_id": riot_id, "riot_tag": riot_tag}
        }), 202

    except Exception as e:
        print("ERROR EN /api/registrar:", e)
        return jsonify({"ok": False, "error": "Ocurrió un error interno al enviar la solicitud."}), 500


# ============================================================
# AGENTE DE WINDOWS: LATIDOS Y CONTROL DE LAS 100 HORAS
# ============================================================

@app.route("/api/agente/latido", methods=["POST"])
def agente_latido():
    datos_recibidos = request.get_json(silent=True) or {}
    nombre = str(datos_recibidos.get("nombre", "")).strip()
    token = str(datos_recibidos.get("token", "")).strip()
    activo = bool(datos_recibidos.get("activo", False))
    if not nombre or not token:
        return jsonify({"ok": False, "error": "Faltan nombre y token del agente."}), 400

    datos = cargar_datos()
    jugadores = datos.get("jugadores", {})
    jugador = jugadores.get(nombre)
    if not jugador or not secrets.compare_digest(str(jugador.get("agente_token", "")), token):
        return jsonify({"ok": False, "error": "Participante o token inválido."}), 403

    inicializar_control_tiempo(jugador)
    ahora = time.time()
    if jugador.get("completado"):
        return jsonify({"ok": True, "completado": True, **tiempo_torneo(jugador)})

    ultimo = jugador.get("agente_ultimo_latido")
    estaba_activo = bool(jugador.get("agente_sesion_activa"))
    # Se acredita el intervalo desde el latido anterior también cuando el cliente
    # acaba de cerrarse. Se limita el salto para no sumar tiempo durante cortes.
    if estaba_activo and ultimo is not None and torneo_en_fecha():
        try:
            delta = max(0, min(LATIDO_MAXIMO_SEGUNDOS, ahora - float(ultimo)))
        except (TypeError, ValueError):
            delta = 0
        jugador["segundos_torneo"] = min(SEGUNDOS_MAXIMOS_TORNEO, int(jugador.get("segundos_torneo", 0)) + int(delta))

    # No se cuenta tiempo antes del 5 ni después del 30 de noviembre (hora argentina).
    activo = activo and torneo_en_fecha()
    jugador["agente_sesion_activa"] = activo
    jugador["agente_ultimo_latido"] = ahora if activo else None
    jugador["agente_ultima_actividad"] = datetime.now(timezone.utc).isoformat()
    finalizar_jugador_si_corresponde(nombre, jugador)
    guardar_datos(datos)
    control = tiempo_torneo(jugador)
    return jsonify({"ok": True, **control, "sesion_activa": bool(jugador.get("agente_sesion_activa"))})


@app.route("/api/agente/estado", methods=["GET"])
def agente_estado():
    nombre = str(request.args.get("nombre", "")).strip()
    token = str(request.args.get("token", "")).strip()
    datos = cargar_datos()
    jugador = datos.get("jugadores", {}).get(nombre)
    if not jugador or not secrets.compare_digest(str(jugador.get("agente_token", "")), token):
        return jsonify({"ok": False, "error": "Participante o token inválido."}), 403
    inicializar_control_tiempo(jugador)
    return jsonify({"ok": True, **tiempo_torneo(jugador)})


# ============================================================
# ADMINISTRACIÓN
# ============================================================

# Esta página no aparece en ningún menú de la web pública.
# Se accede directamente mediante su URL.

@app.route("/admin-soloq-monteros")
def pagina_admin():

    return render_template("admin.html")


@app.route("/api/admin/jugadores", methods=["GET"])
def admin_jugadores():

    try:

        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})

        resultado = []

        for nombre, jugador in jugadores.items():
            resultado.append({
                "nombre": nombre,
                "email": jugador.get("email", ""),
                "riot_id": jugador.get("riot_id", ""),
                "riot_tag": jugador.get("riot_tag", ""),
                "stream_url": jugador.get("stream_url", "")
            })

        return jsonify({
            "ok": True,
            "jugadores": resultado
        })

    except Exception as e:

        print("ERROR EN /api/admin/jugadores:", e)

        return jsonify({
            "ok": False,
            "error": "No se pudieron cargar los jugadores."
        }), 500


@app.route("/api/admin/solicitudes", methods=["GET"])
def admin_solicitudes():

    try:

        datos = cargar_datos()
        solicitudes = datos.get("solicitudes_registro", [])

        if not isinstance(solicitudes, list):
            solicitudes = []

        return jsonify({
            "ok": True,
            "solicitudes": solicitudes
        })

    except Exception as e:

        print("ERROR EN /api/admin/solicitudes:", e)

        return jsonify({
            "ok": False,
            "error": "No se pudieron cargar las solicitudes."
        }), 500


@app.route("/api/admin/solicitudes/aprobar", methods=["POST"])
def admin_aprobar_solicitud():

    try:

        datos_recibidos = request.get_json(silent=True) or {}
        nombre = str(datos_recibidos.get("nombre", "")).strip()

        if not nombre:
            return jsonify({
                "ok": False,
                "error": "Falta el nombre de la solicitud."
            }), 400

        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})
        solicitudes = datos.get("solicitudes_registro", [])

        solicitud_encontrada = None

        for solicitud in solicitudes:
            if str(solicitud.get("nombre", "")).strip().lower() == nombre.lower():
                solicitud_encontrada = solicitud
                break

        if not solicitud_encontrada:
            return jsonify({
                "ok": False,
                "error": "La solicitud ya no existe."
            }), 404

        if nombre in jugadores:
            return jsonify({
                "ok": False,
                "error": "Ese nombre ya está registrado como jugador."
            }), 409

        riot_id = solicitud_encontrada.get("riot_id", "")
        riot_tag = solicitud_encontrada.get("riot_tag", "")
        puuid = solicitud_encontrada.get("puuid")

        for nombre_existente, jugador_existente in jugadores.items():

            if (
                str(jugador_existente.get("riot_id", "")).strip().lower() == str(riot_id).strip().lower()
                and
                str(jugador_existente.get("riot_tag", "")).strip().lower() == str(riot_tag).strip().lower()
            ):
                return jsonify({
                    "ok": False,
                    "error": f"Esa cuenta ya está registrada como {nombre_existente}."
                }), 409

        if not puuid:
            return jsonify({
                "ok": False,
                "error": "La solicitud no tiene PUUID."
            }), 400

        jugadores[nombre] = {
            "email": solicitud_encontrada.get("email", ""),
            "riot_id": riot_id,
            "riot_tag": riot_tag,
            "puuid": puuid,
            "stream_url": solicitud_encontrada.get("stream_url", ""),
            "tiempo_usado": 0,
            "sesion_activa": False,
            "inicio_sesion": None,
            "historial": [],
            "partidas_riot": [],
            "rango": None,
            "ultima_partida": None,
            "segundos_torneo": 0,
            "agente_token": secrets.token_urlsafe(32),
            "agente_ultimo_latido": None,
            "agente_sesion_activa": False,
            "agente_ultima_actividad": None,
            "completado": False,
            "completado_en": None,
            "estadisticas_finales": None
        }

        solicitudes = [
            solicitud
            for solicitud in solicitudes
            if str(solicitud.get("nombre", "")).strip().lower() != nombre.lower()
        ]

        datos["jugadores"] = jugadores
        datos["solicitudes_registro"] = solicitudes
        guardar_datos(datos)

        eliminar_comprobante(solicitud_encontrada.get("comprobante"))

        with bloqueo_estados:
            cache_estados.pop(nombre, None)
            ultima_consulta_estado.pop(nombre, None)

        token_agente = jugadores[nombre]["agente_token"]
        return jsonify({
            "ok": True,
            "mensaje": f"{nombre} aprobado correctamente. Código del agente (compartir en privado con el participante): {token_agente}",
            "token_agente": token_agente
        })

    except Exception as e:

        print("ERROR EN /api/admin/solicitudes/aprobar:", e)

        return jsonify({
            "ok": False,
            "error": "No se pudo aprobar la solicitud."
        }), 500


@app.route("/api/admin/solicitudes/rechazar", methods=["POST"])
def admin_rechazar_solicitud():

    try:

        datos_recibidos = request.get_json(silent=True) or {}
        nombre = str(datos_recibidos.get("nombre", "")).strip()

        if not nombre:
            return jsonify({
                "ok": False,
                "error": "Falta el nombre de la solicitud."
            }), 400

        datos = cargar_datos()
        solicitudes = datos.get("solicitudes_registro", [])

        solicitud_rechazada = next(
            (solicitud for solicitud in solicitudes
             if str(solicitud.get("nombre", "")).strip().lower() == nombre.lower()),
            None
        )

        nuevas_solicitudes = [
            solicitud
            for solicitud in solicitudes
            if str(solicitud.get("nombre", "")).strip().lower() != nombre.lower()
        ]

        if len(nuevas_solicitudes) == len(solicitudes):
            return jsonify({
                "ok": False,
                "error": "La solicitud ya no existe."
            }), 404

        datos["solicitudes_registro"] = nuevas_solicitudes
        guardar_datos(datos)

        if solicitud_rechazada:
            eliminar_comprobante(solicitud_rechazada.get("comprobante"))

        return jsonify({
            "ok": True,
            "mensaje": f"Solicitud de {nombre} rechazada."
        })

    except Exception as e:

        print("ERROR EN /api/admin/solicitudes/rechazar:", e)

        return jsonify({
            "ok": False,
            "error": "No se pudo rechazar la solicitud."
        }), 500


@app.route("/api/consultas", methods=["POST"])
def recibir_consulta():

    try:

        datos_recibidos = request.get_json(silent=True) or {}
        nombre = str(datos_recibidos.get("nombre", "")).strip()
        consulta = str(datos_recibidos.get("consulta", "")).strip()

        if not nombre:
            return jsonify({"ok": False, "error": "Debes ingresar tu nombre."}), 400

        if not consulta:
            return jsonify({"ok": False, "error": "Debes escribir tu consulta."}), 400

        if len(nombre) > 100:
            return jsonify({"ok": False, "error": "El nombre es demasiado largo."}), 400

        if len(consulta) > 2000:
            return jsonify({"ok": False, "error": "La consulta no puede superar los 2000 caracteres."}), 400

        if DATABASE_URL:

            token = uuid.uuid4().hex

            with psycopg.connect(DATABASE_URL) as conexion:
                fila = conexion.execute(
                    """
                    INSERT INTO consultas_registro (nombre, consulta, acceso_token)
                    VALUES (%s, %s, %s)
                    RETURNING id, creada_en, acceso_token
                    """,
                    (nombre, consulta, token)
                ).fetchone()

                conexion.execute(
                    """
                    INSERT INTO consultas_mensajes
                        (consulta_id, autor_tipo, autor_nombre, mensaje)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (fila[0], "participante", nombre, consulta)
                )

            return jsonify({
                "ok": True,
                "mensaje": "Consulta enviada correctamente.",
                "id": fila[0],
                "token": fila[2]
            }), 201

        # Desarrollo local sin PostgreSQL.
        datos = cargar_datos()
        consultas = datos.get("consultas", [])
        if not isinstance(consultas, list):
            consultas = []

        consulta_id = int(time.time() * 1000)
        token = uuid.uuid4().hex

        consultas.append({
            "id": consulta_id,
            "nombre": nombre,
            "consulta": consulta,
            "creada_en": time.strftime("%Y-%m-%d %H:%M:%S"),
            "acceso_token": token,
            "mensajes": [{
                "autor_tipo": "participante",
                "autor_nombre": nombre,
                "mensaje": consulta,
                "creado_en": time.strftime("%Y-%m-%d %H:%M:%S")
            }]
        })

        datos["consultas"] = consultas
        guardar_datos(datos)

        return jsonify({
            "ok": True,
            "mensaje": "Consulta enviada correctamente.",
            "id": consulta_id,
            "token": token
        }), 201

    except Exception as e:
        print("ERROR EN /api/consultas:", e)
        return jsonify({"ok": False, "error": "No se pudo enviar la consulta."}), 500


@app.route("/api/consultas/<int:consulta_id>", methods=["GET"])
def obtener_chat_consulta(consulta_id):

    try:

        token = str(request.args.get("token", "")).strip()
        if not token:
            return jsonify({"ok": False, "error": "Falta el identificador de la conversación."}), 400

        if DATABASE_URL:
            with psycopg.connect(DATABASE_URL) as conexion:
                consulta = conexion.execute(
                    """
                    SELECT id, nombre, consulta,
                           TO_CHAR(creada_en, 'YYYY-MM-DD HH24:MI:SS')
                    FROM consultas_registro
                    WHERE id = %s AND acceso_token = %s
                    """,
                    (consulta_id, token)
                ).fetchone()

                if not consulta:
                    return jsonify({"ok": False, "error": "Conversación no encontrada."}), 404

                filas = conexion.execute(
                    """
                    SELECT id, autor_tipo, autor_nombre, mensaje,
                           TO_CHAR(creado_en, 'YYYY-MM-DD HH24:MI:SS')
                    FROM consultas_mensajes
                    WHERE consulta_id = %s
                    ORDER BY creado_en ASC, id ASC
                    """,
                    (consulta_id,)
                ).fetchall()

            mensajes = [
                {
                    "id": fila[0],
                    "autor_tipo": fila[1],
                    "autor_nombre": fila[2],
                    "mensaje": fila[3],
                    "creado_en": fila[4]
                }
                for fila in filas
            ]

            # Compatibilidad con consultas creadas antes del sistema de chat.
            if not mensajes:
                mensajes = [{
                    "id": None,
                    "autor_tipo": "participante",
                    "autor_nombre": consulta[1],
                    "mensaje": consulta[2],
                    "creado_en": consulta[3]
                }]

            return jsonify({
                "ok": True,
                "consulta": {
                    "id": consulta[0],
                    "nombre": consulta[1],
                    "mensajes": mensajes
                }
            })

        datos = cargar_datos()
        consultas = datos.get("consultas", [])
        if not isinstance(consultas, list):
            consultas = []

        encontrada = None
        for consulta in consultas:
            if int(consulta.get("id", -1)) == consulta_id and consulta.get("acceso_token") == token:
                encontrada = consulta
                break

        if not encontrada:
            return jsonify({"ok": False, "error": "Conversación no encontrada."}), 404

        mensajes = encontrada.get("mensajes", [])
        if not mensajes:
            mensajes = [{
                "autor_tipo": "participante",
                "autor_nombre": encontrada.get("nombre", ""),
                "mensaje": encontrada.get("consulta", ""),
                "creado_en": encontrada.get("creada_en", "")
            }]

        return jsonify({
            "ok": True,
            "consulta": {
                "id": encontrada.get("id"),
                "nombre": encontrada.get("nombre", ""),
                "mensajes": mensajes
            }
        })

    except Exception as e:
        print("ERROR EN /api/consultas/<id>:", e)
        return jsonify({"ok": False, "error": "No se pudo cargar la conversación."}), 500


@app.route("/api/admin/consultas", methods=["GET"])
def admin_consultas():

    try:

        if DATABASE_URL:
            with psycopg.connect(DATABASE_URL) as conexion:
                filas = conexion.execute(
                    """
                    SELECT c.id, c.nombre, c.consulta,
                           TO_CHAR(c.creada_en, 'YYYY-MM-DD HH24:MI:SS'),
                           COUNT(m.id) AS cantidad_mensajes
                    FROM consultas_registro c
                    LEFT JOIN consultas_mensajes m ON m.consulta_id = c.id
                    GROUP BY c.id
                    ORDER BY c.creada_en DESC
                    """
                ).fetchall()

                consultas = []
                for fila in filas:
                    mensajes = conexion.execute(
                        """
                        SELECT id, autor_tipo, autor_nombre, mensaje,
                               TO_CHAR(creado_en, 'YYYY-MM-DD HH24:MI:SS')
                        FROM consultas_mensajes
                        WHERE consulta_id = %s
                        ORDER BY creado_en ASC, id ASC
                        """,
                        (fila[0],)
                    ).fetchall()

                    lista_mensajes = [
                        {
                            "id": m[0],
                            "autor_tipo": m[1],
                            "autor_nombre": m[2],
                            "mensaje": m[3],
                            "creado_en": m[4]
                        }
                        for m in mensajes
                    ]

                    if not lista_mensajes:
                        lista_mensajes = [{
                            "id": None,
                            "autor_tipo": "participante",
                            "autor_nombre": fila[1],
                            "mensaje": fila[2],
                            "creado_en": fila[3]
                        }]

                    consultas.append({
                        "id": fila[0],
                        "nombre": fila[1],
                        "consulta": fila[2],
                        "creada_en": fila[3],
                        "mensajes": lista_mensajes
                    })

        else:
            datos = cargar_datos()
            consultas = datos.get("consultas", [])
            if not isinstance(consultas, list):
                consultas = []

        return jsonify({"ok": True, "consultas": consultas})

    except Exception as e:
        print("ERROR EN /api/admin/consultas:", e)
        return jsonify({"ok": False, "error": "No se pudieron cargar las consultas."}), 500


@app.route("/api/admin/consultas/<int:consulta_id>/responder", methods=["POST"])
def admin_responder_consulta(consulta_id):

    try:

        datos_recibidos = request.get_json(silent=True) or {}
        respuesta = str(datos_recibidos.get("respuesta", "")).strip()
        admin_nombre = str(datos_recibidos.get("admin_nombre", "Administrador")).strip() or "Administrador"

        if not respuesta:
            return jsonify({"ok": False, "error": "Escribí una respuesta."}), 400

        if len(respuesta) > 2000:
            return jsonify({"ok": False, "error": "La respuesta no puede superar los 2000 caracteres."}), 400

        if len(admin_nombre) > 100:
            admin_nombre = admin_nombre[:100]

        if DATABASE_URL:
            with psycopg.connect(DATABASE_URL) as conexion:
                existe = conexion.execute(
                    "SELECT id FROM consultas_registro WHERE id = %s",
                    (consulta_id,)
                ).fetchone()

                if not existe:
                    return jsonify({"ok": False, "error": "Conversación no encontrada."}), 404

                conexion.execute(
                    """
                    INSERT INTO consultas_mensajes
                        (consulta_id, autor_tipo, autor_nombre, mensaje)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (consulta_id, "admin", admin_nombre, respuesta)
                )

            return jsonify({"ok": True, "mensaje": "Respuesta enviada correctamente."}), 201

        datos = cargar_datos()
        consultas = datos.get("consultas", [])
        if not isinstance(consultas, list):
            consultas = []

        for consulta in consultas:
            if int(consulta.get("id", -1)) == consulta_id:
                mensajes = consulta.setdefault("mensajes", [])
                mensajes.append({
                    "autor_tipo": "admin",
                    "autor_nombre": admin_nombre,
                    "mensaje": respuesta,
                    "creado_en": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                datos["consultas"] = consultas
                guardar_datos(datos)
                return jsonify({"ok": True, "mensaje": "Respuesta enviada correctamente."}), 201

        return jsonify({"ok": False, "error": "Conversación no encontrada."}), 404

    except Exception as e:
        print("ERROR EN /api/admin/consultas/<id>/responder:", e)
        return jsonify({"ok": False, "error": "No se pudo enviar la respuesta."}), 500


@app.route("/api/admin/consultas/<int:consulta_id>", methods=["DELETE"])
def admin_borrar_consulta(consulta_id):

    try:

        if DATABASE_URL:
            with psycopg.connect(DATABASE_URL) as conexion:
                fila = conexion.execute(
                    "DELETE FROM consultas_registro WHERE id = %s RETURNING id",
                    (consulta_id,)
                ).fetchone()

                if not fila:
                    return jsonify({"ok": False, "error": "Consulta no encontrada."}), 404

        else:
            datos = cargar_datos()
            consultas = datos.get("consultas", [])
            if not isinstance(consultas, list):
                consultas = []

            nuevas_consultas = [
                consulta for consulta in consultas
                if int(consulta.get("id", -1)) != consulta_id
            ]

            if len(nuevas_consultas) == len(consultas):
                return jsonify({"ok": False, "error": "Consulta no encontrada."}), 404

            datos["consultas"] = nuevas_consultas
            guardar_datos(datos)

        return jsonify({"ok": True, "mensaje": "Conversación eliminada correctamente."})

    except Exception as e:
        print("ERROR EN /api/admin/consultas/<id>:", e)
        return jsonify({"ok": False, "error": "No se pudo eliminar la conversación."}), 500


@app.route("/api/admin/comprobantes/<int:comprobante_id>")
def admin_ver_comprobante(comprobante_id):

    try:
        if not DATABASE_URL:
            return jsonify({"ok": False, "error": "Comprobante no disponible."}), 404

        with psycopg.connect(DATABASE_URL) as conexion:
            fila = conexion.execute(
                "SELECT mime_type, archivo FROM comprobantes_registro WHERE id = %s",
                (comprobante_id,)
            ).fetchone()

        if not fila:
            return jsonify({"ok": False, "error": "Comprobante no encontrado."}), 404

        return send_file(
            BytesIO(bytes(fila[1])),
            mimetype=fila[0],
            download_name="comprobante.jpg" if fila[0] == "image/jpeg" else "comprobante.png"
        )

    except Exception as e:
        print("ERROR AL MOSTRAR COMPROBANTE:", e)
        return jsonify({"ok": False, "error": "No se pudo mostrar el comprobante."}), 500


@app.route("/api/admin/jugadores/<path:nombre>", methods=["DELETE"])
def admin_borrar_jugador(nombre):

    try:

        nombre = nombre.strip()
        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})

        if nombre not in jugadores:
            return jsonify({
                "ok": False,
                "error": "Jugador no encontrado."
            }), 404

        del jugadores[nombre]
        datos["jugadores"] = jugadores
        guardar_datos(datos)

        with bloqueo_estados:
            cache_estados.pop(nombre, None)
            ultima_consulta_estado.pop(nombre, None)

        return jsonify({
            "ok": True,
            "mensaje": f"{nombre} eliminado correctamente."
        })

    except Exception as e:

        print("ERROR EN /api/admin/jugadores:", e)

        return jsonify({
            "ok": False,
            "error": "No se pudo eliminar el jugador."
        }), 500


# ============================================================
# HISTORIAL DE UN JUGADOR
# ============================================================

@app.route("/historial/<nombre>")
def historial_jugador(nombre):

    datos = cargar_datos()


    jugadores = datos.get(
        "jugadores",
        {}
    )


    jugador = jugadores.get(
        nombre
    )


    if not jugador:

        return "Jugador no encontrado", 404


    # ========================================================
    # RANKING ACTUAL
    # ========================================================

    jugadores_ranking = ordenar_jugadores_ranking(
        jugadores
    )


    posicion = None


    for index, (nombre_ranking, _) in enumerate(
        jugadores_ranking
    ):

        if nombre_ranking == nombre:

            posicion = index + 1

            break


    # ========================================================
    # HISTORIAL
    # ========================================================

    partidas = jugador.get(
        "partidas_riot",
        []
    )


    if not isinstance(
        partidas,
        list
    ):

        partidas = []


    partidas = partidas[:5]


    # ========================================================
    # ESTADÍSTICAS
    # ========================================================

    wins = 0
    losses = 0


    for partida in partidas:

        resultado = str(
            partida.get(
                "resultado",
                ""
            )
        ).upper()


        if resultado == "VICTORIA":

            wins += 1


        elif resultado == "DERROTA":

            losses += 1


    partidas_totales = wins + losses


    if partidas_totales > 0:

        wr = round(
            (wins / partidas_totales) * 100
        )

    else:

        wr = 0


    # ========================================================
    # HORAS
    # ========================================================

    control_tiempo = tiempo_torneo(jugador)
    horas_jugadas = control_tiempo["horas_jugadas"]
    horas_disponibles = control_tiempo["horas_restantes"]
    completado = control_tiempo["completado"]


    return render_template(
        "historial.html",
        nombre=nombre,
        jugador=jugador,
        partidas=partidas,
        posicion=posicion,
        wins=wins,
        losses=losses,
        partidas_totales=partidas_totales,
        wr=wr,
        horas_jugadas=horas_jugadas,
        horas_disponibles=horas_disponibles,
        completado=completado
    )


# ============================================================
# API JUGADORES
# ============================================================

@app.route("/api/jugadores")
def api_jugadores():

    try:

        # Actualización de historial/ranking.
        # Solo se ejecutará cuando corresponda.
        actualizar_datos_riot()


        datos = cargar_datos()


        jugadores = datos.get(
            "jugadores",
            {}
        )


        # Estado de partida.
        # Cada jugador solamente genera una consulta REAL
        # cuando su caché de 15 segundos expiró.
        actualizar_estados()


        respuesta = {}


        for nombre, jugador in jugadores.items():

            with bloqueo_estados:

                estado = cache_estados.get(

                    nombre,

                    {
                        "estado": "offline",
                        "game_start_time": None
                    }
                )


            respuesta[nombre] = {

                "riot_id": jugador.get(
                    "riot_id"
                ),

                "riot_tag": jugador.get(
                    "riot_tag"
                ),

                "estado": estado.get(
                    "estado",
                    "offline"
                ),

                "game_start_time": estado.get(
                    "game_start_time"
                ),

                "ultima_partida": jugador.get(
                    "ultima_partida"
                ),

                "rango": jugador.get(
                    "rango"
                ),

                "partidas_riot": jugador.get(
                    "partidas_riot",
                    []
                ),
                "horas_jugadas": tiempo_torneo(jugador)["horas_jugadas"],
                "horas_restantes": tiempo_torneo(jugador)["horas_restantes"],
                "completado": tiempo_torneo(jugador)["completado"],
                "completado_en": tiempo_torneo(jugador)["completado_en"]
            }


        return jsonify(
            respuesta
        )


    except Exception as e:

        print()
        print("ERROR EN /api/jugadores:")
        print(e)
        print()


        return jsonify({
            "error": "Error interno del servidor"
        }), 500


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    puerto = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=False
    )