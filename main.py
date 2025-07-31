from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import requests
import logging
import shutil
import os
import base64
import uuid


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Allow all origins for development purposes only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Confirm that `static` directory exists
if not os.path.isdir("static"):
    logger.warning("Directory 'static' does not exist. Static file serving may fail.")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=FileResponse)
async def root():
    index_path = "static/index.html"
    if not os.path.isfile(index_path):
        logger.error(f"{index_path} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index file not found")
    return FileResponse(index_path)


# ==== Data Models ====


class Query(BaseModel):
    prompt: str
    model: str = "llama3"  # default model


class Message(BaseModel):
    role: str
    content: str


class Conversation(BaseModel):
    id: str
    messages: List[Message] = []


conversations: Dict[str, Conversation] = {}


# ==== Ollama API helpers ====


def call_ollama_generate(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    logger.info(f"Calling Ollama generate endpoint with model='{model}' and prompt='{prompt[:50]}...'")
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        resp_json = response.json()
        return resp_json.get("response", "")
    except requests.RequestException as e:
        err_text = e.response.text if e.response else str(e)
        logger.error(f"Ollama generate API error: {err_text}")
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {err_text}")


def call_ollama_multimodal(model: str, prompt: str, image_path: str) -> str:
    try:
        with open(image_path, "rb") as img_file:
            image_bytes = img_file.read()
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")

        # Try the newer Ollama API format first
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False
        }

        logger.info(f"Calling Ollama multimodal generate API with model={model}")
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        
        if response.status_code == 400:
            # Fall back to chat API format if generate doesn't work
            logger.info("Generate API failed, trying chat API format")
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded_image]
                }
            ]
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
            response = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        
        response.raise_for_status()
        resp_json = response.json()
        
        # Handle both response formats
        if "response" in resp_json:
            return resp_json["response"]
        elif "message" in resp_json and "content" in resp_json["message"]:
            return resp_json["message"]["content"]
        else:
            logger.warning(f"Unexpected response format: {resp_json}")
            return str(resp_json)
            
    except requests.RequestException as e:
        err_text = e.response.text if e.response else str(e)
        logger.error(f"Ollama multimodal API error: {err_text}")
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {err_text}")
    except Exception as e:
        logger.error(f"Unexpected error in multimodal handling: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


# ==== API Endpoints ====


@app.post("/generate", status_code=status.HTTP_200_OK)
async def generate_text(query: Query):
    generated_text = call_ollama_generate(query.model, query.prompt)
    return {"generated_text": generated_text}


@app.options("/generate-multimodal")
async def generate_multimodal_options():
    return {"message": "OK"}

@app.post("/generate-multimodal")
async def generate_multimodal(
    prompt: str = Form(...), 
    model: str = Form(...), 
    file: UploadFile = File(...)
):
    # Log the incoming request
    logger.info(f"Received multimodal request: prompt='{prompt[:50]}...', model='{model}', filename='{file.filename}'")
    
    # Use a random UUID for temp filename suffix to avoid collisions
    ext = os.path.splitext(file.filename)[1] if file.filename else ".img"
    temp_filename = f"temp_{uuid.uuid4().hex}{ext}"
    try:
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if not ext.lower() in (".png", ".jpg", ".jpeg"):
            logger.warning(f"Uploaded file extension '{ext}' is uncommon for images.")

        generated_text = call_ollama_multimodal(model, prompt, temp_filename)
        return {"generated_text": generated_text}
    finally:
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except Exception as e:
            logger.warning(f"Failed to delete temp file '{temp_filename}': {e}")


@app.get("/models", status_code=status.HTTP_200_OK)
async def list_models():
    try:
        logger.info("Fetching available models from Ollama")
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        # Adjust this as per real response key (you may want to log data)
        return {"models": data.get("models", [])}
    except requests.RequestException as e:
        err_text = e.response.text if e.response else str(e)
        logger.error(f"Error fetching models: {err_text}")
        raise HTTPException(status_code=500, detail=f"Error fetching models: {err_text}")


@app.post("/models/download", status_code=status.HTTP_200_OK)
async def download_model(model_name: str = Body(..., embed=True)):
    try:
        logger.info(f"Downloading model: {model_name}")
        response = requests.post(
            "http://localhost:11434/api/pull",
            json={"name": model_name},
            timeout=60,
        )
        response.raise_for_status()
        return {"message": f"Model '{model_name}' downloaded successfully"}
    except requests.RequestException as e:
        err_text = e.response.text if e.response else str(e)
        logger.error(f"Error downloading model: {err_text}")
        raise HTTPException(status_code=500, detail=f"Error downloading model: {err_text}")


@app.post("/conversation/start", status_code=status.HTTP_201_CREATED)
async def start_conversation(conv_id: str = Body(..., embed=True)):
    if conv_id in conversations:
        raise HTTPException(status_code=400, detail="Conversation ID already exists")
    conversations[conv_id] = Conversation(id=conv_id, messages=[])
    logger.info(f"Started new conversation with ID: {conv_id}")
    return {"message": f"Conversation '{conv_id}' started"}


@app.post("/conversation/{conv_id}/message", status_code=status.HTTP_200_OK)
async def add_message(conv_id: str, query: Query):
    if conv_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversations[conv_id]
    conversation.messages.append(Message(role="user", content=query.prompt))

    generated_text = call_ollama_generate(query.model, query.prompt)
    conversation.messages.append(Message(role="assistant", content=generated_text))

    logger.info(f"Conversation '{conv_id}': Added user and assistant messages")
    return {"generated_text": generated_text}


@app.get("/conversation/{conv_id}", response_model=Conversation, status_code=status.HTTP_200_OK)
async def get_conversation(conv_id: str):
    if conv_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conv_id]


@app.get("/debug/routes")
async def list_routes():
    """Debug endpoint to list all available routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods)
            })
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
