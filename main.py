from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
import requests
from fastapi.middleware.cors import CORSMiddleware
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS Middleware — development only, allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html on `/`
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# Data models
class Query(BaseModel):
    prompt: str
    model: str = "llama3"

class Message(BaseModel):
    role: str
    content: str

class Conversation(BaseModel):
    id: str
    messages: List[Message] = []

# In-memory conversations store.
conversations: Dict[str, Conversation] = {}

# Helper function to call Ollama API
def call_ollama_generate(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False  # ensure no streaming for simple response
    }
    try:
        logger.info(f"Calling Ollama API with model={model}")
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        resp_json = response.json()
        generated_text = resp_json.get("response", "")
        logger.info(f"Ollama response received successfully")
        return generated_text
    except requests.RequestException as e:
        logger.error(f"Failed to contact Ollama API: {e}")
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {str(e)}")

# POST /generate - generate a text completion
@app.post("/generate")
async def generate_text(query: Query):
    logger.info(f"Received generate request: {query}")
    generated_text = call_ollama_generate(query.model, query.prompt)
    return {"generated_text": generated_text}

# GET /models - list available models
@app.get("/models")
async def list_models():
    try:
        logger.info("Fetching available models from Ollama")
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        # Ollama returns models info in `models` key typically
        return {"models": data.get("models", [])}
    except requests.RequestException as e:
        logger.error(f"Error fetching models: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching models: {str(e)}")

# POST /models/download - download a model by name
@app.post("/models/download")
async def download_model(model_name: str = Body(..., embed=True)):
    try:
        logger.info(f"Downloading model: {model_name}")
        response = requests.post(
            "http://localhost:11434/api/pull",
            json={"name": model_name},
            timeout=60,  # longer timeout for downloads
        )
        response.raise_for_status()
        return {"message": f"Model '{model_name}' downloaded successfully"}
    except requests.RequestException as e:
        logger.error(f"Error downloading model: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading model: {str(e)}")

# POST /conversation/start — start a new conversation
@app.post("/conversation/start")
async def start_conversation(conv_id: str = Body(..., embed=True)):
    if conv_id in conversations:
        logger.warning(f"Conversation start requested but ID '{conv_id}' already exists")
        raise HTTPException(status_code=400, detail="Conversation ID already exists")
    conversations[conv_id] = Conversation(id=conv_id)
    logger.info(f"Started new conversation with ID '{conv_id}'")
    return {"message": f"Conversation '{conv_id}' started"}

# POST /conversation/{conv_id}/message — add message and get AI response
@app.post("/conversation/{conv_id}/message")
async def add_message(conv_id: str, query: Query):
    if conv_id not in conversations:
        logger.warning(f"Message added to unknown conversation ID '{conv_id}'")
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversations[conv_id]
    # Append user message
    conversation.messages.append({"role": "user", "content": query.prompt})

    # Build prompt combining conversation history for context (optional):
    # For simplicity, here we only send the latest prompt to Ollama.
    # You could enhance by concatenating prior conversation messages.

    generated_text = call_ollama_generate(query.model, query.prompt)

    # Append assistant's response
    conversation.messages.append({"role": "assistant", "content": generated_text})

    logger.info(f"Generated response for conversation '{conv_id}'")
    return {"generated_text": generated_text}

# GET /conversation/{conv_id} — get conversation history
@app.get("/conversation/{conv_id}")
async def get_conversation(conv_id: str):
    if conv_id not in conversations:
        logger.warning(f"Requested conversation '{conv_id}' does not exist.")
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conv_id]

# You can add more endpoints as needed...

# Entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
