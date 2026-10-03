from flask import Flask, render_template, jsonify
import json
import os
import time
import threading

from riot_api import (
    jugador_en_partida,
    obtener_puuid_por_riot_id,
    actualizar_partidas_jugador,
    obtener_rango,
    obtener_ultimo_codigo_http
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

        rate_limit = False

        for nombre, jugador in jugadores.items():

            if rate_limit:
                print(
                    "Riot API está aplicando rate limit."
                )

                print(
                    "Se detiene la actualización "
                    "hasta el próximo ciclo."
                )

                break

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
            # PUUID GUARDADO
            # =================================================

            puuid = jugador.get(
                "puuid"
            )

            if not puuid:

                puuid = obtener_puuid_por_riot_id(
                    riot_id,
                    riot_tag
                )

                codigo = obtener_ultimo_codigo_http()

                if codigo == 429:

                    print(
                        "RATE LIMIT al obtener PUUID."
                    )

                    rate_limit = True
                    break

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

            codigo = obtener_ultimo_codigo_http()

            # =================================================
            # RATE LIMIT
            # =================================================

            if codigo == 429:

                print(
                    f"RATE LIMIT detectado al actualizar "
                    f"{nombre}."
                )

                print(
                    "NO se renovará el PUUID."
                )

                print(
                    "Se conservan los datos actuales."
                )

                rate_limit = True
                break

            # =================================================
            # PUUID INVÁLIDO
            # =================================================

            if partidas is None and codigo == 400:

                print(
                    f"PUUID posiblemente inválido "
                    f"para {nombre}."
                )

                print(
                    "Intentando obtener PUUID nuevo..."
                )

                nuevo_puuid = (
                    obtener_puuid_por_riot_id(
                        riot_id,
                        riot_tag
                    )
                )

                codigo_puuid = (
                    obtener_ultimo_codigo_http()
                )

                # Si volvemos a recibir 429,
                # detenemos el ciclo.
                if codigo_puuid == 429:

                    print(
                        "RATE LIMIT al renovar PUUID."
                    )

                    rate_limit = True
                    break

                if nuevo_puuid:

                    puuid = nuevo_puuid

                    jugador["puuid"] = (
                        nuevo_puuid
                    )

                    print(
                        f"PUUID renovado para {nombre}."
                    )

                    # Reintentar historial.
                    partidas = (
                        actualizar_partidas_jugador(
                            puuid,
                            10
                        )
                    )

                    codigo = (
                        obtener_ultimo_codigo_http()
                    )

                    if codigo == 429:

                        print(
                            "RATE LIMIT durante "
                            "el segundo intento."
                        )

                        rate_limit = True
                        break

                else:

                    print(
                        f"No se pudo renovar PUUID "
                        f"de {nombre}."
                    )

            # =================================================
            # GUARDAR HISTORIAL
            # =================================================

            if partidas is not None:

                jugador["partidas_riot"] = (
                    partidas[:10]
                )

            else:

                print(
                    f"No se pudo actualizar historial "
                    f"de {nombre}."
                )

            # =================================================
            # RANGO
            # =================================================

            rango = obtener_rango(
                puuid
            )

            codigo = obtener_ultimo_codigo_http()

            # =================================================
            # RATE LIMIT EN RANGO
            # =================================================

            if codigo == 429:

                print(
                    f"RATE LIMIT al obtener rango "
                    f"de {nombre}."
                )

                print(
                    "Se conserva el rango anterior."
                )

                rate_limit = True
                break

            # =================================================
            # RANGO CORRECTO
            # =================================================

            if rango is not None:

                jugador["rango"] = rango

                print(
                    f"Rango actualizado para {nombre}: "
                    f"{rango.get('tier')} "
                    f"{rango.get('rank')} "
                    f"{rango.get('lp')} LP"
                )

            else:

                print(
                    f"No se pudo actualizar rango "
                    f"de {nombre}."
                )

                print(
                    "Se conserva el rango anterior."
                )

        # =====================================================
        # GUARDAR
        # =====================================================

        datos["fecha"] = time.strftime(
            "%Y-%m-%d"
        )

        guardar_datos(datos)

        ultima_actualizacion = time.time()

        if rate_limit:

            print(
                "==================================="
            )

            print(
                "ACTUALIZACIÓN INTERRUMPIDA POR RATE LIMIT"
            )

            print(
                "Los datos existentes fueron conservados."
            )

            print(
                "Se volverá a intentar en el próximo ciclo."
            )

            print(
                "==================================="
            )

        else:

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