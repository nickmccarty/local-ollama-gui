const modelSelect = document.getElementById("model");
const promptInput = document.getElementById("prompt");
const generateBtn = document.getElementById("generate");
const responseBox = document.getElementById("responseBox");
const responseText = document.getElementById("responseText");

async function loadModels() {
  try {
    const res = await fetch("http://localhost:8000/models");
    const data = await res.json();
    modelSelect.innerHTML = data.models
      .map(m => `<option value="${m.name}">${m.name}</option>`)
      .join("");
  } catch (err) {
    alert("Error loading models: " + err.message);
  }
}

generateBtn.addEventListener("click", async () => {
  const prompt = promptInput.value.trim();
  const model = modelSelect.value;

  if (!prompt) return alert("Please enter a prompt.");

  generateBtn.disabled = true;
  generateBtn.textContent = "Generating...";

  try {
    const res = await fetch("http://localhost:8000/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, model }),
    });

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
