from flask import Flask, render_template, jsonify
from flask_cors import CORS
import json
import os
import time
import threading

from riot_api import (
    jugador_en_partida,
    obtener_puuid_por_riot_id,
    obtener_summoner_por_puuid,
    actualizar_partidas_jugador,
    obtener_rango,
    obtener_ultimo_codigo_http
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

app = Flask(__name__)

CORS(app, origins=[
    "https://soloqchallenge-monteros.netlify.app"
])

ARCHIVO = "datos.json"

# Actualización de datos pesados de Riot
INTERVALO_ACTUALIZACION = 10 * 60

# Comprobación del estado de los jugadores
INTERVALO_ESTADO = 15


# ============================================================
# VARIABLES GLOBALES
# ============================================================

ultima_actualizacion = 0

bloqueo_actualizacion = threading.Lock()

cache_estados = {}

bloqueo_estados = threading.Lock()


# ============================================================
# CARGAR DATOS
# ============================================================

def cargar_datos():

    try:

        if not os.path.exists(ARCHIVO):

            return {
                "jugadores": {}
            }

        with open(
            ARCHIVO,
            "r",
            encoding="utf-8"
        ) as archivo:

            datos = json.load(archivo)

        if not isinstance(datos, dict):

            return {
                "jugadores": {}
            }

        if "jugadores" not in datos:

            datos["jugadores"] = {}

        if not isinstance(
            datos["jugadores"],
            dict
        ):

            datos["jugadores"] = {}

        return datos

    except (
        json.JSONDecodeError,
        OSError
    ) as e:

        print(
            "ERROR AL CARGAR DATOS:",
            e
        )

        return {
            "jugadores": {}
        }


# ============================================================
# GUARDAR DATOS
# ============================================================

def guardar_datos(datos):

    try:

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

        print(
            "ERROR AL GUARDAR DATOS:",
            e
        )


# ============================================================
# ACTUALIZAR DATOS DE RIOT
# ============================================================

def actualizar_datos_riot():

    global ultima_actualizacion

    # Evitar dos actualizaciones pesadas simultáneas
    if not bloqueo_actualizacion.acquire(
        blocking=False
    ):

        return

    try:

        ahora = time.time()

        # Todavía no corresponde actualizar
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

        for nombre, jugador in jugadores.items():

            print()
            print("Actualizando:", nombre)

            # ==================================================
            # 1. OBTENER PUUID SI NO EXISTE
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

                    print(
                        "ACTUALIZACIÓN DETENIDA."
                    )

                    break

                if not puuid:

                    print(
                        "No se pudo obtener PUUID para:",
                        nombre
                    )

                    continue

                jugador["puuid"] = puuid

                guardar_datos(datos)

                print(
                    "PUUID guardado para:",
                    nombre
                )

            # ==================================================
            # 2. OBTENER SUMMONER ID SI NO EXISTE
            # ==================================================

            summoner_id = jugador.get(
                "summoner_id"
            )

            if not summoner_id:

                print(
                    "No hay Summoner ID guardado."
                )

                print(
                    "Obteniendo Summoner ID..."
                )

                summoner = obtener_summoner_por_puuid(
                    puuid
                )

                codigo = obtener_ultimo_codigo_http()

                if codigo == 429:

                    print(
                        "RATE LIMIT al obtener Summoner ID."
                    )

                    break

                if not summoner:

                    print(
                        "No se pudo obtener Summoner ID para:",
                        nombre
                    )

                    continue

                summoner_id = summoner.get(
                    "id"
                )

                if not summoner_id:

                    print(
                        "El Summoner no tiene ID:",
                        nombre
                    )

                    continue

                jugador["summoner_id"] = summoner_id

                guardar_datos(datos)

                print(
                    "Summoner ID guardado para:",
                    nombre
                )

            # ==================================================
            # 3. ACTUALIZAR HISTORIAL DE PARTIDAS
            # ==================================================

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

                break

            # ==================================================
            # 4. ACTUALIZAR RANGO
            # ==================================================

            try:

                rango = obtener_rango(
                    puuid
                )

                codigo = obtener_ultimo_codigo_http()

                if codigo == 429:

                    print(
                        "RATE LIMIT al obtener rango."
                    )

                    break

                if rango:

                    jugador["rango"] = rango

                    print(
                        f"Rango actualizado para {nombre}: "
                        f"{rango.get('tier', '')} "
                        f"{rango.get('rank', '')} "
                        f"{rango.get('lp', 0)} LP"
                    )

            except Exception as e:

                print(
                    f"Error obteniendo rango de {nombre}:",
                    e
                )

            # ==================================================
            # GUARDAR DESPUÉS DE CADA JUGADOR
            # ==================================================

            guardar_datos(datos)

        # ======================================================
        # FINALIZAR ACTUALIZACIÓN
        # ======================================================

        ultima_actualizacion = time.time()

        datos["fecha"] = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        guardar_datos(datos)

        print()
        print("===================================")
        print("ACTUALIZACIÓN FINALIZADA")
        print("===================================")
        print()

    finally:

        bloqueo_actualizacion.release()


# ============================================================
# OBTENER ESTADO DE UN JUGADOR
# ============================================================

def obtener_estado_jugador(
    nombre,
    jugador
):

    # Utilizamos directamente el Summoner ID
    # guardado en datos.json.

    summoner_id = jugador.get(
        "summoner_id"
    )

    if not summoner_id:

        print(
            f"{nombre}: no tiene Summoner ID guardado."
        )

        return {
            "estado": "offline",
            "game_start_time": None
        }

    try:

        partida = jugador_en_partida(
            summoner_id
        )

        codigo = obtener_ultimo_codigo_http()

        # ====================================================
        # RATE LIMIT
        # ====================================================

        if codigo == 429:

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

        estado = obtener_estado_jugador(
            nombre,
            jugador
        )

        with bloqueo_estados:

            cache_estados[nombre] = estado


# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.route("/")
def inicio():

    return render_template(
        "index.html"
    )


# ============================================================
# API JUGADORES
# ============================================================

@app.route("/api/jugadores")
def api_jugadores():

    try:

        # ====================================================
        # ACTUALIZAR DATOS PESADOS
        # ====================================================

        actualizar_datos_riot()

        # ====================================================
        # CARGAR DATOS ACTUALES
        # ====================================================

        datos = cargar_datos()

        jugadores = datos.get(
            "jugadores",
            {}
        )

        # ====================================================
        # ACTUALIZAR ESTADOS
        # ====================================================

        actualizar_estados()

        # ====================================================
        # CONSTRUIR RESPUESTA
        # ====================================================

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
                )
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