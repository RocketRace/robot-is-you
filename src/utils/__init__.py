from PIL import Image

__all__ = ("Tile", "cached_open")

class Tile:
    '''Represents a tile object, ready to be rendered.'''
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

def cached_open(path, *, cache, is_image=False):
    '''Checks whether a path is in the cache, and if so, returns that element. Otherwise calls open() or Image.open() on the path. '''
    if path in cache:
        return cache[path]
    result = Image.open(path) if is_image else open(path)
    cache[path] = result
    return result