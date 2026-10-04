from flask import Flask, jsonify, render_template
import json
import os
import threading
import time
from riot_api import (
    obtener_puuid_por_riot_id,
    obtener_rango,
    jugador_en_partida,
    actualizar_partidas_jugador
)

app = Flask(__name__)

# Lista de jugadores a monitorear
LISTA_JUGADORES = [
    {"nombre": "Nico", "game_name": "Nico", "tag_line": "LAS"},
    {"nombre": "Lautaro", "game_name": "Lautaro", "tag_line": "LAS"},
    {"nombre": "Petaco", "game_name": "Petaco", "tag_line": "LAS"},
    {"nombre": "Pato", "game_name": "Pato", "tag_line": "LAS"},
    {"nombre": "Parky", "game_name": "Parky", "tag_line": "LAS"},
    {"nombre": "Alebak", "game_name": "Alebak", "tag_line": "LAS"},
    {"nombre": "Facundo", "game_name": "Facundo", "tag_line": "LAS"},
    {"nombre": "Red", "game_name": "Red", "tag_line": "LAS"},
    {"nombre": "Lucas", "game_name": "Lucas", "tag_line": "LAS"}
]

ARCHIVO_DATOS = "datos.json"


def cargar_datos_locales():
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error al leer {ARCHIVO_DATOS}: {e}")
    return []


def guardar_datos_locales(datos):
    try:
        with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error al guardar en {ARCHIVO_DATOS}: {e}")


def actualizar_datos_riot():
    print("===================================")
    print("ACTUALIZANDO DATOS DE RIOT (SEGUNDO PLANO)")
    print("===================================")

    datos_actuales = cargar_datos_locales()
    mapa_actuales = {
        j["nombre"]: j for j in datos_actuales if isinstance(j, dict) and "nombre" in j
    }

    nuevos_datos = []

    for item in LISTA_JUGADORES:
        nombre = item["nombre"]
        game_name = item["game_name"]
        tag_line = item["tag_line"]

        print(f"Actualizando: {nombre}")

        previo = mapa_actuales.get(nombre, {})
        puuid = previo.get("puuid")

        if not puuid:
            puuid = obtener_puuid_por_riot_id(game_name, tag_line)

        if not puuid:
            print(f"No se pudo obtener PUUID para {nombre}.")
            if previo:
                nuevos_datos.append(previo)
            continue

        # 1. Rango
        rango_info = obtener_rango(puuid)
        if not rango_info and previo.get("rango"):
            print(f"No se pudo actualizar rango de {nombre}. Se conserva el rango anterior.")
            rango_info = previo["rango"]

        # 2. Partida Activa
        partida_activa = jugador_en_partida(puuid)

        # 3. Historial de Partidas (Máximo 5 para evitar Rate Limit)
        partidas_historial = actualizar_partidas_jugador(puuid, cantidad=5)
        if partidas_historial is None and previo.get("partidas"):
            partidas_historial = previo["partidas"]

        jugador_estructurado = {
            "nombre": nombre,
            "game_name": game_name,
            "tag_line": tag_line,
            "puuid": puuid,
            "rango": rango_info,
            "en_partida": partida_activa,
            "partidas": partidas_historial or []
        }

        nuevos_datos.append(jugador_estructurado)
        time.sleep(1)  # Pausa de seguridad entre jugadores

    guardar_datos_locales(nuevos_datos)
    print("===================================")
    print("ACTUALIZACIÓN COMPLETADA Y GUARDADA")
    print("===================================")


def bucle_background():
    """Bucle infinito que actualiza en segundo plano sin congelar la app."""
    while True:
        try:
            actualizar_datos_riot()
        except Exception as e:
            print(f"Error en bucle de segundo plano: {e}")

        # Espera 4 minutos (240s) entre cada ciclo de actualización
        time.sleep(240)


# Se inicia el hilo en segundo plano al arrancar el servidor
hilo_actualizacion = threading.Thread(target=bucle_background, daemon=True)
hilo_actualizacion.start()


# =========================================================
# RUTAS FLASK
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/jugadores", methods=["GET"])
def api_jugadores():
    # Respuesta instantánea desde el archivo local
    datos = cargar_datos_locales()
    return jsonify(datos)


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto)