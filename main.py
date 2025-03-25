import aigame


class Game:
    def __init__(self):
        aigame.init()

    def step(self) -> aigame.GameState:
        return aigame.update()

    def render(self):
        aigame.draw()

    def close(self):
        aigame.close()


game = Game()

print(game.step().cells)

game.close()
