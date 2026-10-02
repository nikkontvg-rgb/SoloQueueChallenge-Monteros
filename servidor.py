from flask import Flask, render_template, jsonify
import json
import os

from riot_api import jugador_en_partida


app = Flask(__name__)

ARCHIVO = "datos.json"


def cargar_datos():
    if not os.path.exists(ARCHIVO):
        return {"jugadores": {}}

    with open(ARCHIVO, "r", encoding="utf-8") as archivo:
        return json.load(archivo)


@app.route("/")
def inicio():
    datos = cargar_datos()
    jugadores = datos.get("jugadores", {})

    return render_template(
        "index.html",
        jugadores=jugadores
    )


@app.route("/api/jugadores")
def api_jugadores():

    datos = cargar_datos()
    jugadores = datos.get("jugadores", {})

    resultado = {}

    for nombre, jugador in jugadores.items():

        puuid = jugador.get("puuid")

        # Por defecto
        estado = "offline"

        # Si tiene PUUID, consultamos Riot
        if puuid:

            if jugador_en_partida(puuid):
                estado = "in_game"

        resultado[nombre] = {
            "riot_id": jugador.get("riot_id", ""),
            "riot_tag": jugador.get("riot_tag", ""),
            "estado": estado
        }

    return jsonify(resultado)


if __name__ == "__main__":
    import os

    puerto = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=False
    )