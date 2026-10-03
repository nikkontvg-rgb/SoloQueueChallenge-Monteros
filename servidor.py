from flask import Flask, render_template, jsonify
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


app = Flask(__name__)

ARCHIVO = "datos.json"

INTERVALO_ACTUALIZACION = 10 * 60
INTERVALO_ESTADO = 15

ultima_actualizacion = 0

bloqueo_actualizacion = threading.Lock()

cache_estados = {}
bloqueo_estados = threading.Lock()


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

            riot_id = jugador.get("riot_id")
            riot_tag = jugador.get("riot_tag")

            if not riot_id or not riot_tag:
                continue

            print(f"Actualizando: {nombre}")

            # =================================================
            # PUUID
            # =================================================

            puuid = jugador.get("puuid")

            if not puuid:

                puuid = obtener_puuid_por_riot_id(
                    riot_id,
                    riot_tag
                )

                codigo = obtener_ultimo_codigo_http()

                if codigo == 429:
                    print("RATE LIMIT al obtener PUUID.")
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

            if codigo == 429:

                print(
                    f"RATE LIMIT al actualizar {nombre}."
                )

                rate_limit = True
                break

            # =================================================
            # PUUID INVALIDO
            # =================================================

            if partidas is None and codigo == 400:

                print(
                    f"PUUID rechazado para {nombre}."
                )

                print(
                    "Intentando renovar PUUID mediante Riot ID..."
                )

                nuevo_puuid = obtener_puuid_por_riot_id(
                    riot_id,
                    riot_tag
                )

                codigo_puuid = obtener_ultimo_codigo_http()

                if codigo_puuid == 429:

                    print(
                        "RATE LIMIT al renovar PUUID."
                    )

                    rate_limit = True
                    break

                if nuevo_puuid:

                    puuid = nuevo_puuid

                    jugador["puuid"] = nuevo_puuid

                    print(
                        f"PUUID renovado para {nombre}."
                    )

                    partidas = actualizar_partidas_jugador(
                        puuid,
                        10
                    )

                    codigo = obtener_ultimo_codigo_http()

                    if codigo == 429:

                        print(
                            "RATE LIMIT durante el segundo intento."
                        )

                        rate_limit = True
                        break

            # =================================================
            # HISTORIAL
            # =================================================

            if partidas is not None:

                if partidas:

                    jugador["partidas_riot"] = (
                        partidas[:10]
                    )

                elif "partidas_riot" not in jugador:

                    jugador["partidas_riot"] = []

            # =================================================
            # RANGO
            # =================================================

            rango_anterior = jugador.get("rango")

            rango = obtener_rango(puuid)

            codigo = obtener_ultimo_codigo_http()

            if codigo == 429:

                print(
                    f"RATE LIMIT al obtener rango de {nombre}."
                )

                rate_limit = True
                break

            if rango is None:

                print(
                    f"No se pudo actualizar rango de {nombre}."
                )

                print(
                    "Se conserva el rango anterior."
                )

            elif rango.get("tier") == "UNRANKED":

                if rango_anterior and rango_anterior.get("tier") not in (
                    None,
                    "",
                    "UNRANKED"
                ):

                    print(
                        f"Riot devolvió UNRANKED para {nombre}, "
                        "pero existe un rango válido anterior."
                    )

                    print(
                        "Se conserva el rango anterior."
                    )

                else:

                    jugador["rango"] = rango

            else:

                jugador["rango"] = rango

                print(
                    f"Rango actualizado para {nombre}: "
                    f"{rango.get('tier')} "
                    f"{rango.get('rank')} "
                    f"{rango.get('lp')} LP"
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

            print("===================================")
            print("ACTUALIZACIÓN DETENIDA POR RATE LIMIT")
            print("Los datos anteriores fueron conservados.")
            print("Se reintentará en el próximo ciclo.")
            print("===================================")

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
# ESTADO DE PARTIDA
# =========================================================

def obtener_estado_jugador(nombre, jugador):

    ahora = time.time()

    with bloqueo_estados:

        estado_guardado = cache_estados.get(nombre)

        if estado_guardado:

            tiempo_cache = estado_guardado.get(
                "timestamp",
                0
            )

            if ahora - tiempo_cache < INTERVALO_ESTADO:

                return {
                    "estado": estado_guardado.get(
                        "estado",
                        "offline"
                    ),
                    "game_start_time":
                        estado_guardado.get(
                            "game_start_time"
                        )
                }

    puuid = jugador.get("puuid")

    if not puuid:

        return {
            "estado": "offline",
            "game_start_time": None
        }

    # =========================================================
    # PRIMER INTENTO
    # =========================================================

    print(
        f"Consultando estado de {nombre}..."
    )

    partida = jugador_en_partida(
        puuid
    )

    codigo = obtener_ultimo_codigo_http()

    # =========================================================
    # RATE LIMIT
    # =========================================================

    if codigo == 429:

        print(
            f"RATE LIMIT consultando estado de {nombre}."
        )

        with bloqueo_estados:

            anterior = cache_estados.get(nombre)

            if anterior:

                return {
                    "estado": anterior.get(
                        "estado",
                        "offline"
                    ),
                    "game_start_time":
                        anterior.get(
                            "game_start_time"
                        )
                }

        return {
            "estado": "offline",
            "game_start_time": None
        }

    # =========================================================
    # PUUID INVALIDO
    # =========================================================

    if codigo == 400:

        riot_id = jugador.get("riot_id")
        riot_tag = jugador.get("riot_tag")

        if riot_id and riot_tag:

            print(
                f"PUUID rechazado al consultar estado de {nombre}."
            )

            print(
                "Renovando PUUID mediante Riot ID..."
            )

            nuevo_puuid = obtener_puuid_por_riot_id(
                riot_id,
                riot_tag
            )

            codigo_puuid = obtener_ultimo_codigo_http()

            if codigo_puuid == 429:

                print(
                    f"RATE LIMIT renovando PUUID de {nombre}."
                )

                with bloqueo_estados:

                    anterior = cache_estados.get(nombre)

                    if anterior:

                        return {
                            "estado": anterior.get(
                                "estado",
                                "offline"
                            ),
                            "game_start_time":
                                anterior.get(
                                    "game_start_time"
                                )
                        }

                return {
                    "estado": "offline",
                    "game_start_time": None
                }

            if nuevo_puuid:

                # Guardamos el nuevo PUUID
                jugador["puuid"] = nuevo_puuid

                # Guardamos también en datos.json
                datos = cargar_datos()

                jugadores = datos.get(
                    "jugadores",
                    {}
                )

                if nombre in jugadores:

                    jugadores[nombre]["puuid"] = nuevo_puuid

                    guardar_datos(datos)

                puuid = nuevo_puuid

                print(
                    f"PUUID renovado para {nombre}."
                )

                print(
                    "Volviendo a consultar partida activa..."
                )

                # =================================================
                # SEGUNDO INTENTO CON PUUID NUEVO
                # =================================================

                partida = jugador_en_partida(
                    puuid
                )

                codigo = obtener_ultimo_codigo_http()

                if codigo == 429:

                    print(
                        f"RATE LIMIT durante segundo intento de {nombre}."
                    )

                    with bloqueo_estados:

                        anterior = cache_estados.get(nombre)

                        if anterior:

                            return {
                                "estado": anterior.get(
                                    "estado",
                                    "offline"
                                ),
                                "game_start_time":
                                    anterior.get(
                                        "game_start_time"
                                    )
                            }

                    return {
                        "estado": "offline",
                        "game_start_time": None
                    }

                print(
                    f"Segundo intento de estado para {nombre}: "
                    f"HTTP {codigo}"
                )

            else:

                print(
                    f"No se pudo renovar PUUID de {nombre}."
                )

    # =========================================================
    # RESULTADO
    # =========================================================

    if partida:

        print(
            f"{nombre} está EN PARTIDA."
        )

        estado = {
            "estado": "in_game",
            "game_start_time":
                partida.get(
                    "game_start_time"
                ),
            "timestamp": time.time()
        }

    else:

        print(
            f"{nombre} está OFFLINE."
        )

        estado = {
            "estado": "offline",
            "game_start_time": None,
            "timestamp": time.time()
        }

    with bloqueo_estados:

        cache_estados[nombre] = estado

    return {
        "estado": estado["estado"],
        "game_start_time":
            estado["game_start_time"]
    }


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

        estado_info = obtener_estado_jugador(
            nombre,
            jugador
        )

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

            "estado":
                estado_info.get(
                    "estado",
                    "offline"
                ),

            "game_start_time":
                estado_info.get(
                    "game_start_time"
                ),

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