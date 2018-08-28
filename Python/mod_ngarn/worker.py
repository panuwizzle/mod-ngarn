import asyncio
import logging
import sys
import time

import asyncpg

from mod_ngarn.connection import get_connection

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('mod_ngarn')


async def fetch_job(cnx: asyncpg.Connection):
    return await cnx.fetchrow("""
        SELECT id, fn_name, args, kwargs
        FROM modngarn_job 
        WHERE executed IS NULL
            AND (scheduled IS NULL OR scheduled < NOW())
        ORDER BY priority 
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """)


async def import_fn(function_name: str):
    access_path = function_name.split('.')
    module = None
    for index in range(1, len(access_path)):
        try:
            # import top level module
            module_name = '.'.join(access_path[:-index])
            module = __import__(module_name)
        except ImportError:
            continue
        else:
            for step in access_path[1:-1]: # walk down it
                # import pdb; pdb.set_trace()
                module = getattr(module, step)
            break
    if module:
        return getattr(module, access_path[-1])
    else:
        return globals()['__builtins__'][function_name]


async def execute(cnx: asyncpg.Connection, job: asyncpg.Record):
    """ Execute the transaction """
    func = await import_fn(job['fn_name'])
    if asyncio.iscoroutinefunction(func):
        return await func(cnx, *job['args'], **job['kwargs'])
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, cnx, *job['args'], **job['kwargs'])


async def record_result(cnx: asyncpg.Connection, job: asyncpg.Record, result: dict ={}, error: bool=False):
    """ Record result to database, does not commit the transaction """
    if not error:
        return await cnx.execute("""
            UPDATE modngarn_job SET result=$1, executed=NOW() WHERE id=$2
        """, result, job['id'])
    else:
        return await cnx.execute("""
            UPDATE modngarn_job SET priority=priority+1 WHERE id=$1
        """, job['id'])

async def run():
    cnx = await get_connection()
    async with cnx.transaction():
        job = await fetch_job(cnx)
        if job:
            log.info("Processing#{}".format(job['id']))
            try:
                start_time = time.time()
                result = await execute(cnx, job)
                processed_time = time.time() - start_time
                log.info(' Processed#{} in {}s'.format(job['id'], processed_time))
                await record_result(cnx, job, {'process_time': processed_time, 'result': result})
            # TODO: More specific Exception
            except Exception as e:
                log(str(e))
                await record_result(cnx, job, error=True)
                
    cnx.close()


def run_worker():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())

if __name__ == '__main__':
    run_worker()