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

INTERVALO_ACTUALIZACION = 10 * 60

ultima_actualizacion = 0

bloqueo_actualizacion = threading.Lock()


def cargar_datos():
    if not os.path.exists(ARCHIVO):
        return {"jugadores": {}}

    with open(ARCHIVO, "r", encoding="utf-8") as archivo:
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


def actualizar_datos_riot():

    global ultima_actualizacion

    ahora = time.time()

    if ahora - ultima_actualizacion < INTERVALO_ACTUALIZACION:
        return

    if not bloqueo_actualizacion.acquire(blocking=False):
        return

    try:

        ahora = time.time()

        if ahora - ultima_actualizacion < INTERVALO_ACTUALIZACION:
            return

        print("===================================")
        print("ACTUALIZANDO DATOS DE RIOT")
        print("===================================")

        datos = cargar_datos()
        jugadores = datos.get("jugadores", {})

        for nombre, jugador in jugadores.items():

            riot_id = jugador.get("riot_id", "")
            riot_tag = jugador.get("riot_tag", "")

            if not riot_id or not riot_tag:
                continue

            print(f"Actualizando: {nombre}")

            # --------------------------------
            # OBTENER PUUID
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
                print(f"No se pudo obtener PUUID de {nombre}")
                continue

            # --------------------------------
            # ACTUALIZAR HISTORIAL
            # --------------------------------

            partidas = actualizar_partidas_jugador(
                puuid,
                10
            )

            if partidas:

                jugador["partidas_riot"] = partidas[:10]

            # --------------------------------
            # ACTUALIZAR RANGO
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


@app.route("/api/jugadores")
def api_jugadores():

    # Actualizar historial y ranking
    # como máximo una vez cada 10 minutos

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

        resultado[nombre] = {

            "riot_id": riot_id,

            "riot_tag": riot_tag,

            "estado": estado,

            "game_start_time": game_start_time,

            "rango": jugador.get(
                "rango"
            ),

            "partidas_riot": jugador.get(
                "partidas_riot",
                []
            )
        }

    return jsonify(resultado)


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