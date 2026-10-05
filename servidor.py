from flask import Flask, render_template, jsonify
from flask_cors import CORS
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

ARCHIVO = "datos.json"

INTERVALO_ACTUALIZACION = 10 * 60

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

    if not bloqueo_actualizacion.acquire(
        blocking=False
    ):

        return

    try:

        ahora = time.time()

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
            # 3. ACTUALIZAR RANGO
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

            guardar_datos(datos)

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
# OBTENER ESTADO
# ============================================================

def obtener_estado_jugador(
    nombre,
    jugador
):

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

    try:

        print()
        print(
            f"Consultando estado de {nombre}..."
        )

        partida = jugador_en_partida(
            puuid
        )

        codigo = obtener_ultimo_codigo_http()

        if codigo == 429:

            print(
                f"{nombre}: RATE LIMIT."
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

        estado = obtener_estado_jugador(
            nombre,
            jugador
        )

        with bloqueo_estados:

            cache_estados[nombre] = estado


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def inicio():

    return render_template(
        "index.html"
    )


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
    #
    # POR AHORA se calculan con las partidas almacenadas.
    # Más adelante tendremos estadísticas acumuladas
    # independientes del historial de 5 partidas.
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
    #
    # TEMPORALMENTE QUEDAN EN 0.
    # El sistema acumulable de 4 horas se programa después.
    # ========================================================

    horas_jugadas = 0

    horas_disponibles = 4

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
        horas_disponibles=horas_disponibles
    )


# ============================================================
# API JUGADORES
# ============================================================

@app.route("/api/jugadores")
def api_jugadores():

    try:

        actualizar_datos_riot()

        datos = cargar_datos()

        jugadores = datos.get(
            "jugadores",
            {}
        )

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