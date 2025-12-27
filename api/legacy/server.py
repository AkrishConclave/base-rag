from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from ingest import run_ingest
from query import answer_question

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/ask")
async def ask(payload: dict):
    question = payload.get("q", "").strip()
    if not question:
        return {"error": "empty question"}
    ans, sources = answer_question(question)
    return {"answer": ans, "sources": sources}

@app.post("/ingest")
async def ingest():
    count = run_ingest()
    return {"indexed_chunks": count}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9001)
