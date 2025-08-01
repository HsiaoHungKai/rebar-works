from flask import Flask, json, request, jsonify
from datetime import datetime, timezone
import random
import os
from functools import wraps
from config import REQUIRED_KEYS, OPTIONAL_KEYS
from dotenv import load_dotenv

app = Flask(__name__)


def api_response(status, message, pairs=None):
    response = {
        "caseID": request.form["caseID"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
    }
    
    if pairs:
        response["pairs"] = pairs

    return jsonify(response), status


def require_bearer_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return api_response(status=401, message="缺少 Authorization header")

        # Check if it starts with "Bearer "
        if not auth_header.startswith("Bearer "):
            return api_response(
                status=401,
                message="Authorization header 格式錯誤，應為 'Bearer <token>'",
            )

        # Extract the token
        token = auth_header.split(" ")[1]

        # Validate the token
        load_dotenv()  # Load environment variables from .env file
        token_string = os.getenv("TOKENS")
        VALID_TOKENS = json.loads(token_string)
        if token not in VALID_TOKENS:
            return api_response(status=401, message="無效的 token")

        # Token is valid, proceed with the original function
        return f(*args, **kwargs)

    return decorated_function


@app.route("/", methods=["POST"])
@require_bearer_token  # Add this decorator
def receive_distances():
    try:
        # 檢查是否有form-data
        if not request.form:
            return api_response(
                status=400,
                message="請提供表單資料",
            )

        # 檢查必要欄位
        for key, expected_type in REQUIRED_KEYS.items():
            # 檢查是否有提供必要欄位
            if key not in request.form:
                return api_response(
                    status=400,
                    message=f"缺少必要欄位: {key}",
                )
            # 檢查欄位是否為空
            if not request.form[key]:
                return api_response(
                    status=400,
                    message=f"欄位 {key} 不能為空",
                )
            # 檢查資料型別
            try:
                # 嘗試cast欄位值為預期的資料型別
                expected_type(request.form[key])
            except ValueError:
                return api_response(
                    status=400,
                    message=f"欄位 {key} 的資料型別錯誤，應為 {expected_type.__name__}。",
                )

        # 檢查是否有提供 sensor_width 或 device-model 其中一個
        sensor_width = request.form.get("sensor_width")
        device_model = request.form.get("device-model")
        if not sensor_width and not device_model:
            return api_response(
                status=400,
                message="請提供 sensor_width 或 device-model 其中一個欄位",
            )
        # 檢查資料型別（只針對有值的欄位進行）
        for key, expected_type in OPTIONAL_KEYS.items():
            value = request.form.get(key)
            if value:  # 有值才檢查型別
                try:
                    expected_type(value)
                except ValueError:
                    return api_response(
                        status=400,
                        message=f"欄位 {key} 的資料型別錯誤，應為 {expected_type.__name__}。",
                    )

        # 檢查是否提供影像檔
        if "image" not in request.files:
            return api_response(
                status=400,
                message="缺少影像檔",
            )
        image_file = request.files.getlist("image")
        if len(image_file) > 1:
            return api_response(
                status=400,
                message="僅支援單一影像檔上傳",
            )
        # 檢查影像檔案是否為空
        image_file = image_file[0]  # 取出單一影像檔
        if image_file.filename == "":
            return api_response(
                status=400,
                message="未選擇影像檔案",
            )
        # 檢查檔案格式
        allowed_extensions = {".png", ".jpg"}
        file_extension = os.path.splitext(image_file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            return api_response(
                status=400,
                message="檔案格式不支援，僅接受 PNG, JPG 格式",
            )

        # 模擬三組點與距離
        def random_point():
            return {"x": random.randint(0, 1024), "y": random.randint(0, 768)}

        pairs = []
        for _ in range(3):
            p1 = random_point()
            p2 = random_point()
            distance = round(random.uniform(10.0, 300.0), 2)
            pairs.append({"start_point": p1, "end_point": p2, "distance": distance})

        return api_response(
            status=200,
            message="深度重建成功",
            pairs=pairs,
        )

    except Exception as e:
        return api_response(
            status=500,
            message=f"伺服器錯誤: {str(e)}",
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

