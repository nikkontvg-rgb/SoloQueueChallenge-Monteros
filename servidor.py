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

    if not bloqueo_actualizacion.acquire(
        blocking=False
    ):
        return

    try:

        ahora = time.time()

        if ahora - ultima_actualizacion < INTERVALO_ACTUALIZACION:
            return

        print("===================================")
        print("ACTUALIZANDO DATOS DE RIOT")
        print("===================================")

        datos = cargar_datos()

        jugadores = datos.get(
            "jugadores",
            {}
        )

        for nombre, jugador in jugadores.items():

            riot_id = jugador.get(
                "riot_id"
            )

            riot_tag = jugador.get(
                "riot_tag"
            )

            if not riot_id or not riot_tag:
                continue

            print(
                f"Actualizando: {nombre}"
            )

            # =================================================
            # OBTENER PUUID NUEVO
            # =================================================

            puuid_guardado = jugador.get(
                "puuid"
            )

            puuid = puuid_guardado

            # Primero intentamos usar el PUUID guardado.
            # Si las APIs lo rechazan, más abajo se renueva.

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

            # =================================================
            # HISTORIAL
            # =================================================

            partidas = actualizar_partidas_jugador(
                puuid,
                10
            )

            # Si el PUUID guardado es inválido,
            # Riot suele devolver None.
            #
            # En ese caso obtenemos nuevamente el PUUID
            # directamente mediante Riot ID + TAG.

            if partidas is None:

                print(
                    f"PUUID inválido para {nombre}. "
                    "Renovando PUUID..."
                )

                nuevo_puuid = (
                    obtener_puuid_por_riot_id(
                        riot_id,
                        riot_tag
                    )
                )

                if nuevo_puuid:

                    puuid = nuevo_puuid

                    jugador["puuid"] = (
                        nuevo_puuid
                    )

                    print(
                        f"PUUID renovado para {nombre}"
                    )

                    partidas = (
                        actualizar_partidas_jugador(
                            puuid,
                            10
                        )
                    )

            if partidas:

                jugador["partidas_riot"] = (
                    partidas[:10]
                )

            # =================================================
            # RANGO
            # =================================================

            rango = obtener_rango(
                puuid
            )

            # Si el rango falla, conservamos
            # el rango anterior.

            if rango is not None:

                jugador["rango"] = rango

            else:

                print(
                    f"No se pudo actualizar "
                    f"el rango de {nombre}. "
                    "Se conserva el anterior."
                )

        # =====================================================
        # GUARDAR
        # =====================================================

        datos["fecha"] = time.strftime(
            "%Y-%m-%d"
        )

        guardar_datos(datos)

        ultima_actualizacion = time.time()

        print(
            "DATOS ACTUALIZADOS CORRECTAMENTE"
        )

    except Exception as error:

        print(
            "ERROR ACTUALIZANDO DATOS:"
        )

        print(error)

    finally:

        bloqueo_actualizacion.release()


# =========================================================
# PAGINA PRINCIPAL
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

                game_start_time = (
                    partida.get(
                        "game_start_time"
                    )
                )

        # =====================================================
        # ULTIMA PARTIDA
        # =====================================================

        partidas = jugador.get(
            "partidas_riot",
            []
        )

        ultima_partida = None

        if partidas:

            ultima_partida = (
                partidas[0].get(
                    "fecha"
                )
            )

        resultado[nombre] = {

            "riot_id": riot_id,

            "riot_tag": riot_tag,

            "estado": estado,

            "game_start_time":
                game_start_time,

            "ultima_partida":
                ultima_partida,

            "rango":
                jugador.get(
                    "rango"
                ),

            "partidas_riot":
                partidas
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