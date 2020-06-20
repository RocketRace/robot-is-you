
class Tile:
    def __init__(self, name = None, variant = None, color = None, source = "vanilla", images = []):
        self.name = name
        self.variant = variant
        self.color = None if color is None else tuple(color)
        self.source = source
        self.custom = len(images) > 0
        self.images = images

    def __repr__(self):
        if self.custom:
            return f"<Custom tile {self.name}>"
        return f"<Tile {self.name} : {self.variant} with {self.color} from {self.source}>"