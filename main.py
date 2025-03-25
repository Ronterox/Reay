import aigame


class Game:
    def __init__(self):
        aigame.init()

    def step(self):
        aigame.update()

    def render(self):
        aigame.draw()

    def close(self):
        aigame.close()


game = Game()

while True:
    game.step()
    game.render()

game.close()
