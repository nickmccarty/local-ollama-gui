const modelSelect = document.getElementById("model");
const promptInput = document.getElementById("prompt");
const fileInput = document.getElementById("fileInput");
const fileUploadSection = document.getElementById("fileUploadSection");
const generateBtn = document.getElementById("generate");
const responseBox = document.getElementById("responseBox");
const responseText = document.getElementById("responseText");

const multimodalModels = ["gpt-4-vision", "llava", "custom-multimodal", "llama3.2-vision:latest"]; // extend as needed

async function loadModels() {
  try {
    const res = await fetch("/models");
    const data = await res.json();

    if (!Array.isArray(data.models) || data.models.length === 0) {
      modelSelect.innerHTML = '<option value="llama3">llama3 (default)</option>';
      alert("No models found from server. Using fallback.");
      return;
    }

    modelSelect.innerHTML = data.models
      .map(m => `<option value="${m.name}">${m.name}</option>`)
      .join("");

    toggleFileUpload(modelSelect.value);
  } catch (err) {
    alert("Error loading models: " + err.message);
    modelSelect.innerHTML = '<option value="llama3">llama3 (default)</option>';
  }
}

// Toggle file upload section visibility
function toggleFileUpload(model) {
  fileUploadSection.hidden = !multimodalModels.includes(model);
}

// Trigger visibility change on model change
modelSelect.addEventListener("change", () => {
  toggleFileUpload(modelSelect.value);
});

generateBtn.addEventListener("click", async () => {
  const prompt = promptInput.value.trim();
  const model = modelSelect.value;
  const isMultimodal = multimodalModels.includes(model);
  const file = fileInput?.files?.[0];

  if (!prompt) return alert("Please enter a prompt.");

  if (isMultimodal && !file) {
    return alert("Please upload a file for this model.");
  }

  generateBtn.disabled = true;
  generateBtn.textContent = "Generating...";
  responseText.textContent = "";
  responseBox.hidden = true;

  try {
    let res;

    if (isMultimodal) {
      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("model", model);
      formData.append("file", file);

      res = await fetch("/generate-multimodal", {
        method: "POST",
        body: formData,
      });
    } else {
      res = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, model }),
      });
    }

    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Server error: ${errorText}`);
    }

    const data = await res.json();
    responseText.textContent = data.generated_text || "No response.";
    responseBox.hidden = false;
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "Generate";
  }
});

loadModels();
