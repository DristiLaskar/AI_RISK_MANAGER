import os
import shutil
from typing import List

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.analysis import (BASE, UPLOAD_DIR, clients_payload, dashboard_payload, forecast_payload,
                           get_analysis)
from core.auth import router as auth_router

app = FastAPI(title="AI Risk Manager")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)


def _reset_uploads():
    for f in os.listdir(UPLOAD_DIR):
        os.remove(os.path.join(UPLOAD_DIR, f))


def _analysis_or_400():
    try:
        return get_analysis()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


_reset_uploads()  # every server start begins empty


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    _reset_uploads()
    saved = []
    for f in files:
        if f.filename.lower().endswith((".csv", ".xlsx")):
            with open(os.path.join(UPLOAD_DIR, os.path.basename(f.filename)), "wb") as out:
                out.write(await f.read())
            saved.append(f.filename)
    if not saved:
        raise HTTPException(status_code=400, detail="Upload a .csv or .xlsx file.")
    try:
        get_analysis()
    except ValueError as e:                    # surface bad files now, not as a blank dashboard later
        _reset_uploads()
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "files": saved}


@app.post("/demo")
def load_demo():
    _reset_uploads()
    for name in ("transactions.csv", "invoices.csv"):
        shutil.copy(os.path.join(BASE, "data", name), UPLOAD_DIR)
    get_analysis()
    return {"status": "ok"}


class ManualEntry(BaseModel):
    rows: List[dict]    # {date, client_id, amount, type?}


@app.post("/manual-entry")
def manual_entry(data: ManualEntry):
    if not data.rows:
        raise HTTPException(status_code=400, detail="Add at least one payment.")
    _reset_uploads()
    pd.DataFrame(data.rows).to_csv(os.path.join(UPLOAD_DIR, "manual_entry.csv"), index=False)
    try:
        get_analysis()
    except ValueError as e:
        _reset_uploads()
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


def _payload(builder):
    res = _analysis_or_400()
    return {"no_data": True} if res is None else builder(res)


@app.get("/dashboard")
def get_dashboard():
    return _payload(dashboard_payload)


@app.get("/clients")
def get_clients():
    return _payload(clients_payload)


@app.get("/forecast")
def get_forecast():
    return _payload(forecast_payload)


@app.get("/download-clients")
def download_clients():
    res = _analysis_or_400()
    if res is None:
        raise HTTPException(status_code=404, detail="No data loaded.")
    csv = pd.DataFrame(clients_payload(res)["clients"]).to_csv(index=False)
    return Response(csv, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=client_analysis.csv"})


class Question(BaseModel):
    question: str


@app.post("/ask")
def ask(q: Question):
    res = _analysis_or_400()
    if res is None:
        raise HTTPException(status_code=400, detail="Load some data first.")
    return res["rag"].answer(q.question)


# the React app (built into frontend/dist) is served from the same origin
app.mount("/", StaticFiles(directory=os.path.join(BASE, "frontend"), html=True), name="ui")
