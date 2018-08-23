from worker import import_fn
import pytest

# TEST functions
async def async_ret(text):
    import asyncio
    await asyncio.sleep(1)
    return text


def sync_ret(text):
    return text


@pytest.mark.asyncio
async def test_import_fn_can_import_builtin_fn():
    s = await import_fn("sum")
    res = s([1,2,3])
    assert res == 6


@pytest.mark.asyncio
async def test_import_fn_can_import_sync_fn():
    r = await import_fn("tests.test_import_fn.sync_ret")
    res = r('Hello')
    assert res == "Hello"


@pytest.mark.asyncio
async def test_import_fn_can_import_async_fn():
    r = await import_fn("tests.test_import_fn.async_ret")
    res = await r('Hello')
    assert res == "Hello"
