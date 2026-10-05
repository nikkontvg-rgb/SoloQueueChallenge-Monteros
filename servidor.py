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

# Actualización de historial + ranking cada 10 minutos
INTERVALO_ACTUALIZACION = 10 * 60

# Estado de partida: máximo 1 consulta cada 15 segundos
# por jugador
INTERVALO_ESTADO = 15

# Cuando Riot devuelve 429, esperamos 60 segundos
# antes de volver a consultar.
PAUSA_RATE_LIMIT = 60


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

        # Si estamos retomando después de un Rate Limit,
        # indice_proximo_jugador será mayor que 0 y NO
        # debemos aplicar el intervalo de 10 minutos.

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


            # Pausa global para evitar seguir golpeando
            # la API mientras está limitando las solicitudes.
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