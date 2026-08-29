from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from huggingface_hub import hf_hub_download
from ultralytics import YOLO
from PIL import Image
import io
import database  # Import the local database file

app = Flask(__name__)
CORS(app)

# Initialize the SQLite database on startup
database.init_db()

print("Downloading model weights...")
model_path = hf_hub_download(
    repo_id="kendrickfff/waste-classification-yolov8-ken", 
    filename="yolov8n-waste-12cls-best.pt"
)

print("Loading model into memory...")
model = YOLO(model_path)

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

@app.route("/detect", methods=["POST"])
def detect_waste():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    try:
        # 1. Capture Image
        image_file = request.files["image"]
        image = Image.open(io.BytesIO(image_file.read())).convert("RGB")
        
        # 2. Capture Frontend Metadata (GPS and User details)
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        user_id = request.form.get("user_id", "guest_user")

        # 3. Run AI Inference
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

                    # 4. Log successful detection into SQLite
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
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
