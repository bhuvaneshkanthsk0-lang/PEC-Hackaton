from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from huggingface_hub import hf_hub_download
from ultralytics import YOLO
from PIL import Image
import io
import database  # Imports your local database.py file

app = Flask(__name__)
CORS(app)

# 1. Initialize the SQLite database on startup
database.init_db()

# 2. Download model weights safely
print("Downloading model weights...")
model_path = hf_hub_download(
    repo_id="kendrickfff/waste-classification-yolov8-ken", 
    filename="yolov8n-waste-12cls-best.pt"
)

# 3. Load model into memory
print("Loading model into memory...")
model = YOLO(model_path)

# 4. Scrap prices mapping
SCRAP_PRICES = {
    "battery": 50.0,
    "biological": 0.0,
    "brown-glass": 3.0,
    "cardboard": 10.0,
    "clothes": 5.0,
    "green-glass": 3.0,
    "metal": 30.0,
    "paper": 8.0,
    "plastic": 15.0,
    "shoes": 10.0,
    "trash": 0.0,
    "white-glass": 4.0
}

# 5. Web UI Template (Now with GPS Geolocation)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EcoTrack AI - Waste Detector</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #1e293b; padding: 2rem; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); width: 100%; max-width: 480px; }
        h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #22c55e; }
        p { color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }
        input[type="file"] { width: 100%; padding: 0.5rem; margin-bottom: 1rem; background: #334155; border-radius: 6px; color: #f8fafc; border: 1px solid #475569; }
        button { width: 100%; background: #22c55e; color: #0f172a; font-weight: bold; border: none; padding: 0.75rem; border-radius: 6px; cursor: pointer; font-size: 1rem; transition: background 0.2s; }
        button:hover { background: #16a34a; }
        #results { margin-top: 1.5rem; background: #0f172a; padding: 1rem; border-radius: 8px; border: 1px solid #334155; display: none; }
        pre { color: #38bdf8; font-size: 0.85rem; overflow-x: auto; margin: 0; }
        .highlight { color: #facc15; font-weight: bold; }
    </style>
</head>
<body>
    <div class="card">
        <h1>EcoTrack AI</h1>
        <p>Upload or snap a waste photo to identify type, value, and location.</p>
        
        <form id="uploadForm">
            <input type="file" id="imageInput" name="image" accept="image/*" required>
            <button type="submit" id="submitBtn">Detect Waste</button>
        </form>

        <div id="results">
            <h3 style="margin-top:0; color:#f8fafc;">Detection Summary</h3>
            <p id="summaryText" style="margin-bottom: 0.5rem;"></p>
            <pre><code id="jsonOutput"></code></pre>
        </div>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        const resultsDiv = document.getElementById('results');
        const jsonOutput = document.getElementById('jsonOutput');
        const summaryText = document.getElementById('summaryText');
        const submitBtn = document.getElementById('submitBtn');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('imageInput');
            if (!fileInput.files[0]) return;

            submitBtn.innerText = "Locating & Analyzing...";
            submitBtn.disabled = true;

            const formData = new FormData();
            formData.append('image', fileInput.files[0]);
            
            // Hardcode a test user ID for now
            formData.append('user_id', 'pec_hacks_tester_01'); 

            // Request GPS Location from the browser
            if ("geolocation" in navigator) {
                navigator.geolocation.getCurrentPosition(
                    async (position) => {
                        // User allowed location: append coordinates
                        formData.append('latitude', position.coords.latitude);
                        formData.append('longitude', position.coords.longitude);
                        await sendToBackend(formData);
                    },
                    async (error) => {
                        // User denied location or it failed: proceed without GPS
                        console.warn("Location access denied or unavailable.");
                        await sendToBackend(formData);
                    }
                );
            } else {
                // Browser doesn't support geolocation
                await sendToBackend(formData);
            }
        });

        // Send the combined Image + GPS data to Flask
        async function sendToBackend(formData) {
            try {
                const res = await fetch('/detect', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await res.json();
                
                if (!res.ok) {
                    throw new Error(data.error || 'Server error');
                }
                
                resultsDiv.style.display = 'block';
                jsonOutput.innerText = JSON.stringify(data, null, 2);

                if (data.status === 'success' && data.total_items > 0) {
                    summaryText.innerHTML = `Found <span class="highlight">${data.total_items} items</span> | Total Est. Value: <span class="highlight">₹${data.total_value}</span>`;
                } else {
                    summaryText.innerText = 'No waste items detected.';
                }
            } catch (err) {
                alert(`Error processing image: ${err.message}`);
            } finally {
                submitBtn.innerText = "Detect Waste";
                submitBtn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/detect", methods=["POST"])
def detect_waste():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    try:
        # Capture Image
        image_file = request.files["image"]
        image = Image.open(io.BytesIO(image_file.read())).convert("RGB")
        
        # Capture Frontend Metadata (GPS and User details)
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        user_id = request.form.get("user_id", "guest_user")

        # Run AI Inference
        results = model(image)
        
        detected_items = []
        total_estimated_value = 0.0

        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = model.names[class_id].lower()

                if confidence > 0.40:
                    item_price = SCRAP_PRICES.get(class_name, 0.0)
                    total_estimated_value += item_price

                    # Log successful detection and location into SQLite
                    database.log_scan(
                        user_id=user_id,
                        item_type=class_name,
                        estimated_value=item_price,
                        lat=latitude,
                        lon=longitude
                    )

                    detected_items.append({
                        "item": class_name,
                        "confidence": round(confidence, 2),
                        "estimated_value": item_price,
                        "bounding_box": [round(coord, 2) for coord in box.xyxy[0].tolist()]
                    })

        return jsonify({
            "status": "success",
            "total_items": len(detected_items),
            "total_value": round(total_estimated_value, 2),
            "detections": detected_items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Debug and reloader disabled to prevent Windows multithreading deadlocks
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
