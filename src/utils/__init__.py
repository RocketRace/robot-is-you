from typing import Any, Dict, List, Optional, Tuple, TypeVar
from PIL import Image

class Tile:
    '''Represents a tile object, ready to be rendered.'''
    def __init__(
        self,
        *,
        name: Optional[str] = None,
        variant: Optional[int] = None,
        color: Optional[Tuple[int, int]] = None,
        source: str = "vanilla",
        meta_level: int = 0,
        style: Optional[str] = None,
        custom: bool = False,
        images: Optional[List[Image.Image]] = None
    ):
        self.name = name
        self.variant = variant
        self.color = color
        self.source = source
        self.style = style
        self.meta_level = meta_level
        self.custom = custom
        self.images = images or []

    def __repr__(self) -> str:
        if self.custom:
            return f"<Custom tile {self.name}>"
        return f"<Tile {self.name} : {self.variant} with {self.color} from {self.source}>"

def cached_open(path, *, cache: Dict[str, Any], is_image: bool = False) -> Any:
    '''Checks whether a path is in the cache, and if so, returns that element. Otherwise calls open() or Image.open() on the path. '''
    if path in cache:
        return cache[path]
    result = Image.open(path) if is_image else open(path)
    cache[path] = result
    return result