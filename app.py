import os
import json
import shutil
import io
from pathlib import Path
from flask import Flask, render_template, jsonify, send_file, request
from PIL import Image, ImageOps
import rawpy

app = Flask(__name__)

CURRENT_DIR = Path(__file__).parent
SOURCE_DIR = Path(r"E:\PROJECT\WEDDING\DILA & FAKHRI\P\AJAR")
BRIDE_DIR = CURRENT_DIR / "Bride_Picks"
GROOM_DIR = CURRENT_DIR / "Groom_Picks"
STATE_FILE = CURRENT_DIR / "_culler_state.json"
REVIEW_ORDER_FILE = CURRENT_DIR / "review_order.json"
DUPLICATES_FILE = CURRENT_DIR / "duplicates.json"

BRIDE_DIR.mkdir(exist_ok=True)
GROOM_DIR.mkdir(exist_ok=True)

def load_json(filepath, default_val):
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    return default_val

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    order = load_json(REVIEW_ORDER_FILE, [])
    dupes_list = load_json(DUPLICATES_FILE, [])
    state = load_json(STATE_FILE, {"current_index": 0, "tags": {}, "categories": {}})

    duplicates_map = {}
    photo_to_group_index = {}
    for idx, group in enumerate(dupes_list, 1):
        for photo in group:
            duplicates_map[photo] = group
            photo_to_group_index[photo] = idx

    # Hitung statistik untuk HUD atas
    total = len(order)
    tagged_count = 0
    s_count = 0
    d_count = 0
    both_count = 0
    
    for p in order:
        t = state["tags"].get(p, {"bride": False, "groom": False})
        b = t.get("bride", False)
        g = t.get("groom", False)
        if b or g:
            tagged_count += 1
        if b and g:
            both_count += 1
        elif b:
            s_count += 1
        elif g:
            d_count += 1
    none_count = total - tagged_count

    return jsonify({
        "photos": order,
        "duplicates": duplicates_map,
        "group_indices": photo_to_group_index,
        "state": state,
        "stats": {
            "total": total,
            "tagged": tagged_count,
            "bride": s_count,
            "groom": d_count,
            "both": both_count,
            "none": none_count
        }
    })

@app.route("/api/tag", methods=["POST"])
def toggle_tag():
    data = request.json
    filename = data["filename"]
    reviewer = data["reviewer"]

    state = load_json(STATE_FILE, {"current_index": 0, "tags": {}, "categories": {}})
    
    if filename not in state["tags"]:
        state["tags"][filename] = {"bride": False, "groom": False}
        
    state["tags"][filename][reviewer] = not state["tags"][filename][reviewer]
    state["current_index"] = data.get("current_index", state["current_index"])
    
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

    source_file = SOURCE_DIR / filename
    target_dir = BRIDE_DIR if reviewer == "bride" else GROOM_DIR
    target_file = target_dir / filename

    if state["tags"][filename][reviewer]:
        if source_file.exists() and not target_file.exists():
            shutil.copy2(source_file, target_file)
    else:
        if target_file.exists():
            target_file.unlink()

    return jsonify({"success": True})

@app.route("/api/clear", methods=["POST"])
def clear_tags():
    data = request.json
    filename = data["filename"]
    state = load_json(STATE_FILE, {"current_index": 0, "tags": {}, "categories": {}})
    
    if filename in state["tags"]:
        for reviewer in ["bride", "groom"]:
            if state["tags"][filename].get(reviewer):
                target_file = (BRIDE_DIR if reviewer == "bride" else GROOM_DIR) / filename
                if target_file.exists():
                    target_file.unlink()
        state["tags"][filename] = {"bride": False, "groom": False}
        
    state["current_index"] = data.get("current_index", state["current_index"])
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
        
    return jsonify({"success": True})

@app.route("/img/<filename>")
def serve_image(filename):
    path = SOURCE_DIR / filename
    if not path.exists():
        return "Not found", 404

    try:
        if path.suffix.lower() in {".cr2", ".arw", ".nef", ".dng"}:
            with rawpy.imread(str(path)) as raw:
                try:
                    thumb = raw.extract_thumb()
                    return send_file(io.BytesIO(thumb.data), mimetype='image/jpeg')
                except Exception:
                    img = Image.fromarray(raw.postprocess(half_size=True))
        else:
            img = Image.open(path)
            
        img = ImageOps.exif_transpose(img)
        img_io = io.BytesIO()
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
        
    except Exception as e:
        print(f"Error memuat gambar {filename}: {e}")
        return "Error loading image", 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)