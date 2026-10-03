from flask import Flask, render_template, jsonify
import json
import os
import time
import threading

from riot_api import (
    jugador_en_partida,
    obtener_puuid_por_riot_id,
    actualizar_partidas_jugador,
    obtener_rango
)


app = Flask(__name__)

ARCHIVO = "datos.json"

# Riot se actualiza como máximo cada 10 minutos
INTERVALO_ACTUALIZACION = 10 * 60

ultima_actualizacion = 0

bloqueo_actualizacion = threading.Lock()


# =========================================================
# DATOS
# =========================================================

def cargar_datos():

    if not os.path.exists(ARCHIVO):
        return {"jugadores": {}}

    with open(
        ARCHIVO,
        "r",
        encoding="utf-8"
    ) as archivo:

        return json.load(archivo)


def guardar_datos(datos):

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


# =========================================================
# ACTUALIZACIÓN DE RIOT
# =========================================================

def actualizar_datos_riot():

    global ultima_actualizacion

    ahora = time.time()

    if ahora - ultima_actualizacion < INTERVALO_ACTUALIZACION:
        return

    if not bloqueo_actualizacion.acquire(blocking=False):
        return

    try:

        # Volvemos a comprobar el tiempo después de obtener
        # el bloqueo para evitar actualizaciones duplicadas.
        ahora = time.time()

        if ahora - ultima_actualizacion < INTERVALO_ACTUALIZACION:
            return

        print("===================================")
        print("ACTUALIZANDO DATOS DE RIOT")
        print("===================================")

        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})

        for nombre, jugador in jugadores.items():

            riot_id = jugador.get("riot_id")
            riot_tag = jugador.get("riot_tag")

            if not riot_id or not riot_tag:
                continue

            print(f"Actualizando: {nombre}")

            # --------------------------------
            # PUUID
            # --------------------------------

            puuid = jugador.get("puuid")

            if not puuid:

                puuid = obtener_puuid_por_riot_id(
                    riot_id,
                    riot_tag
                )

                if puuid:
                    jugador["puuid"] = puuid

            if not puuid:

                print(
                    f"No se pudo obtener PUUID de {nombre}"
                )

                continue

            # --------------------------------
            # HISTORIAL
            # --------------------------------

            partidas = actualizar_partidas_jugador(
                puuid,
                10
            )

            if partidas:
                jugador["partidas_riot"] = partidas[:10]

            # --------------------------------
            # RANGO
            # --------------------------------

            rango = obtener_rango(puuid)

            if rango:
                jugador["rango"] = rango

        # --------------------------------
        # GUARDAR
        # --------------------------------

        datos["fecha"] = time.strftime(
            "%Y-%m-%d"
        )

        guardar_datos(datos)

        ultima_actualizacion = time.time()

        print("DATOS ACTUALIZADOS CORRECTAMENTE")

    except Exception as error:

        print("ERROR ACTUALIZANDO DATOS:")
        print(error)

    finally:

        bloqueo_actualizacion.release()


# =========================================================
# PÁGINA PRINCIPAL
# =========================================================

@app.route("/")
def inicio():

    datos = cargar_datos()

    jugadores = datos.get(
        "jugadores",
        {}
    )

    return render_template(
        "index.html",
        jugadores=jugadores
    )


# =========================================================
# API DE JUGADORES
# =========================================================

@app.route("/api/jugadores")
def api_jugadores():

    # Actualiza historial y ranking como máximo
    # una vez cada 10 minutos.
    actualizar_datos_riot()

    datos = cargar_datos()

    jugadores = datos.get(
        "jugadores",
        {}
    )

    resultado = {}

    for nombre, jugador in jugadores.items():

        riot_id = jugador.get(
            "riot_id",
            ""
        )

        riot_tag = jugador.get(
            "riot_tag",
            ""
        )

        # -------------------------------------------------
        # ESTADO
        # -------------------------------------------------
        #
        # Actualmente Riot solamente nos permite detectar
        # si está dentro de una partida.
        #
        # El estado "online" quedará preparado para la
        # futura aplicación externa.
        # -------------------------------------------------

        estado = "offline"
        game_start_time = None

        if riot_id and riot_tag:

            partida = jugador_en_partida(
                riot_id,
                riot_tag
            )

            if partida:

                estado = "in_game"

                game_start_time = partida.get(
                    "game_start_time"
                )

        # -------------------------------------------------
        # ÚLTIMA PARTIDA
        # -------------------------------------------------

        partidas = jugador.get(
            "partidas_riot",
            []
        )

        ultima_partida = None

        if partidas:

            ultima_partida = partidas[0].get(
                "fecha"
            )

        # -------------------------------------------------
        # RESULTADO
        # -------------------------------------------------

        resultado[nombre] = {

            "riot_id": riot_id,

            "riot_tag": riot_tag,

            "estado": estado,

            "game_start_time": game_start_time,

            "ultima_partida": ultima_partida,

            "rango": jugador.get(
                "rango"
            ),

            "partidas_riot": partidas
        }

    return jsonify(resultado)


# =========================================================
# SERVIDOR
# =========================================================

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