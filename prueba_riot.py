import requests
from config import API_KEY


GAME_NAME = "RBL Ace"
TAG_LINE = "ARG"


url = (
    "https://americas.api.riotgames.com"
    f"/riot/account/v1/accounts/by-riot-id/"
    f"{GAME_NAME}/{TAG_LINE}"
)


headers = {
    "X-Riot-Token": API_KEY
}


respuesta = requests.get(url, headers=headers)


print("Código de respuesta:", respuesta.status_code)

print("Respuesta de Riot:")

print(respuesta.text)