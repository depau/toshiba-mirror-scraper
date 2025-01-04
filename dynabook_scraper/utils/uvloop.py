try:
    # noinspection PyUnresolvedReferences
    import uvloop

    uvloop_available = True
except ImportError:
    uvloop_available = False


def async_run(*a, **kw):
    if uvloop_available:
        return uvloop.run(*a, **kw)
    else:
        return asyncio.run(*a, **kw)
