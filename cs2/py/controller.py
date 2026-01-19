from py.map import Map

from rcon.source import Client


class Controller:
    def __init__(self, host, port, password) -> None:
        self.host = host
        self.port = port
        self.password = password

    def restart(self):
        with Client(self.host, int(self.port), passwd=self.password) as client:
            response = client.run("mp_restartgame", "1")

        print(response)

    def change_map(self, map: Map, mode: str):
        print(f"Sending RCON request to change to map '{map.name}' and game alias '{mode}'")

        with Client(self.host, int(self.port), passwd=self.password) as client:
            if map.workshop:
                response = client.run("game_alias", mode, ";", "host_workshop_map", map.id)
            else:
                response = client.run("game_alias", mode, ";", "map", map.id)

        print(response)
