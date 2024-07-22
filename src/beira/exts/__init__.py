from pkgutil import iter_modules


EXTENSIONS = [mod_info.name for mod_info in iter_modules(__path__, f"{__package__}.")]
