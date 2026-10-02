from riot_api import jugador_en_partida

PUUID = "ACA_VA_EL_PUUID"

resultado = jugador_en_partida(PUUID)

if resultado:
    print("🎮 EL JUGADOR ESTÁ EN PARTIDA")
else:
    print("⚪ EL JUGADOR NO ESTÁ EN PARTIDA")