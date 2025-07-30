from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
import requests
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

# CORS Middleware — allow all origins for development only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files under /static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at root
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# Data models
class Query(BaseModel):
    prompt: str
    model: str = "llama3"

class Conversation(BaseModel):
    id: str
    messages: List[Dict[str, str]] = []

# In-memory conversation store
conversations: Dict[str, Conversation] = {}

# POST /generate — generate text using Ollama API
@app.post("/generate")
async def generate_text(query: Query):
    print(f"Received generate request: {query}")  # Debug logging
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": query.model, "prompt": query.prompt},
            timeout=15,
        )
        response.raise_for_status()
        return {"generated_text": response.json().get("response", "")}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {str(e)}")

# Alternative endpoint for debugging
@app.post("/generate-debug")
async def generate_text_debug(request: Request):
    body = await request.body()
    print(f"Raw request body: {body}")
    try:
        data = json.loads(body)
        print(f"Parsed data: {data}")
        query = Query(**data)
        return await generate_text(query)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=400, detail=f"Request parsing error: {str(e)}")

# GET /models — list available models from Ollama
@app.get("/models")
async def list_models():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        response.raise_for_status()
        return {"models": response.json().get("models", [])}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching models: {str(e)}")

# POST /models/download — download a model by name (expect JSON body with model_name)
@app.post("/models/download")
async def download_model(model_name: str = Body(..., embed=True)):
    try:
        response = requests.post(
            "http://localhost:11434/api/pull",
            json={"name": model_name},
            timeout=30,
        )
        response.raise_for_status()
        return {"message": f"Model '{model_name}' downloaded successfully"}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error downloading model: {str(e)}")

# POST /conversation/start — start a new conversation with given conv_id (query param or JSON body)
@app.post("/conversation/start")
async def start_conversation(conv_id: str = Body(..., embed=True)):
    if conv_id in conversations:
        raise HTTPException(status_code=400, detail="Conversation ID already exists")
    conversations[conv_id] = Conversation(id=conv_id)
    return {"message": f"Conversation '{conv_id}' started"}

# POST /conversation/{conv_id}/message — add message and get AI response
@app.post("/conversation/{conv_id}/message")
async def add_message(conv_id: str, query: Query):
    if conv_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversations[conv_id]
    conversation.messages.append({"role": "user", "content": query.prompt})

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": query.model, "prompt": query.prompt},
            timeout=15,
        )
        response.raise_for_status()
        generated_text = response.json().get("response", "")
        conversation.messages.append({"role": "assistant", "content": generated_text})
        return {"generated_text": generated_text}
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {str(e)}")

# GET /conversation/{conv_id} — get conversation history
@app.get("/conversation/{conv_id}")
async def get_conversation(conv_id: str):
    if conv_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conv_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
