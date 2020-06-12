
class Tile:
    def __init__(self, name = None, variant = None, color = None, source = "vanilla"):
        self.name = name
        self.variant = variant
        self.color = None if color is None else tuple(color)
        self.source = source

    def __repr__(self):
        return f"<Tile {self.name} : {self.variant} with {self.color} from {self.source}>"