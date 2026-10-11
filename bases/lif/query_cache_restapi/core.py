from typing import List
from fastapi import FastAPI, HTTPException

from lif.datatypes import LIFFragment, LIFQuery, LIFQueryFilter, LIFRecord, LIFUpdate
from lif.exceptions.core import InvalidInputException, ResourceNotFoundException
from lif.logging.core import get_logger
from lif.query_cache_service.core import add, query, save, update

app = FastAPI()
logger = get_logger(__name__)


@app.get("/")
def root() -> dict:
    return {"message": "Hello World!"}


@app.post("/query", response_model=List[LIFRecord])
async def do_load(lif_query: LIFQuery) -> List[LIFRecord]:
    logger.info("CALL RECEIVED TO /query API")
    try:
        return await query(lif_query)
    except ValueError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update", response_model=LIFRecord)
async def do_run_update(lif_update: LIFUpdate) -> LIFRecord:
    logger.info("CALL RECEIVED TO /update API")
    try:
        return await update(lif_update)
    except ValueError:
        raise
    except InvalidInputException as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/add", response_model=LIFRecord)
async def do_add_record(lif_record: LIFRecord) -> LIFRecord:
    logger.info("CALL RECEIVED TO /add API")
    try:
        return await add(lif_record=lif_record)
    except ValueError:
        raise
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save")
async def do_save_record(lif_query_filter: LIFQueryFilter, lif_fragments: List[LIFFragment]):
    logger.info("CALL RECEIVED TO /save API")
    try:
        return await save(lif_query_filter=lif_query_filter, lif_fragments=lif_fragments)
    except ValueError:
        raise
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
