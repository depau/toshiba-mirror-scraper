import io

try:
    import orjson

    loads = orjson.loads

    def dumps(obj, *args, **kwargs):
        if "indent" in kwargs:
            indent = kwargs.pop("indent")
            if indent and indent > 0:
                kwargs["option"] = kwargs.get("option", 0) | orjson.OPT_INDENT_2
        return orjson.dumps(obj, *args, **kwargs)

    def load(fp):
        return orjson.loads(fp.read())

    def dump(obj, fp, *args, **kwargs):
        res = dumps(obj, *args, **kwargs)
        if isinstance(fp, io.TextIOBase):
            fp.write(res.decode())
        else:
            fp.write(res)

    async def aload(fp):
        return orjson.loads(await fp.read())

    async def adump(obj, fp, *args, **kwargs):
        res = dumps(obj, *args, **kwargs)
        try:
            await fp.write(res)
        except TypeError:
            await fp.write(res.decode())

except ImportError:
    print("orjson not found, falling back to json")
    from json import *
