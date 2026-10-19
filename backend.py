import os
import csv
import re
import threading
import webbrowser
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory, send_file
from PIL import Image, ImageFilter

import speech_recognition as sr
from rembg import remove, new_session


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HTML_FILE = os.path.join(BASE_DIR, "index.html")
CSV_FILE = os.path.join(BASE_DIR, "backgrounds.csv")
BACKGROUND_FOLDER = os.path.join(BASE_DIR, "backgrounds")


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# REMBG
# ============================================================

print("Loading rembg model...")
print("This may take some time the first time.")

try:
    REMBG_SESSION = new_session("u2net")
    print("rembg model loaded.")
except Exception as e:
    print("ERROR loading rembg:")
    print(e)
    REMBG_SESSION = None


# ============================================================
# SPEECH RECOGNITION
# ============================================================

recognizer = sr.Recognizer()

# These values are deliberately not extremely aggressive.
# The microphone is adjusted only briefly and then speech is
# listened for normally.
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8
recognizer.phrase_threshold = 0.2
recognizer.non_speaking_duration = 0.5


# ============================================================
# BACKGROUND DATA
# ============================================================

background_records = []


def load_backgrounds():
    global background_records

    background_records = []

    if not os.path.exists(CSV_FILE):
        print("WARNING: backgrounds.csv not found.")
        return

    try:
        with open(
            CSV_FILE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:
                background_records.append(row)

        print(
            f"Loaded {len(background_records)} background records."
        )

    except Exception as e:
        print("ERROR reading backgrounds.csv:")
        print(e)


load_backgrounds()


# ============================================================
# FIND BACKGROUND FILE
# ============================================================

def find_background_file(img_id):
    """
    CSV img_id 1 -> img2
    CSV img_id 2 -> img3
    ...
    CSV img_id 40 -> img41
    """

    filename_number = int(img_id) + 1

    extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    ]

    for extension in extensions:

        filename = f"img{filename_number}{extension}"

        path = os.path.join(
            BACKGROUND_FOLDER,
            filename
        )

        if os.path.isfile(path):
            return filename

    return None


# ============================================================
# BACKGROUND API
# ============================================================

@app.route("/api/backgrounds")
def get_backgrounds():

    result = []

    for record in background_records:

        try:
            img_id = int(record.get("img_id", "").strip())
        except Exception:
            continue

        img_name = record.get(
            "img_name",
            f"Background {img_id}"
        ).strip()

        filename = find_background_file(img_id)

        if filename is None:
            continue

        result.append({
            "img_id": img_id,
            "name": img_name,
            "filename": filename,
            "url": f"/backgrounds/{filename}"
        })

    return jsonify(result)


# ============================================================
# SERVE BACKGROUND IMAGES
# ============================================================

@app.route("/backgrounds/<path:filename>")
def serve_background(filename):

    return send_from_directory(
        BACKGROUND_FOLDER,
        filename
    )


# ============================================================
# FRONTEND
# ============================================================

@app.route("/")
def index():

    if not os.path.isfile(HTML_FILE):
        return (
            "ERROR: index.html was not found in the project folder.",
            500
        )

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# IMAGE PROCESSING
# ============================================================

def remove_background(input_image):

    if REMBG_SESSION is None:
        raise RuntimeError(
            "rembg model is not available."
        )

    output = remove(
        input_image,
        session=REMBG_SESSION
    )

    return output.convert("RGBA")


def fit_background(background, size):

    target_width, target_height = size

    background = background.convert("RGB")

    bg_width, bg_height = background.size

    scale = max(
        target_width / bg_width,
        target_height / bg_height
    )

    new_width = int(bg_width * scale)
    new_height = int(bg_height * scale)

    background = background.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS
    )

    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2

    background = background.crop(
        (
            left,
            top,
            left + target_width,
            top + target_height
        )
    )

    return background


def make_background_removal(input_image):

    """
    Option 1:
    Remove background and return transparent image.
    """

    return remove_background(input_image)


def make_blurred_background(input_image):

    """
    Option 2:
    Keep the person/object and blur the background.
    """

    foreground = remove_background(input_image)

    original = input_image.convert("RGB")

    blurred = original.filter(
        ImageFilter.GaussianBlur(radius=15)
    )

    result = blurred.convert("RGBA")

    result.alpha_composite(
        foreground
    )

    return result


def make_custom_background(
    input_image,
    background_path
):

    """
    Replace the original background with the
    selected image.
    """

    foreground = remove_background(input_image)

    background = Image.open(
        background_path
    ).convert("RGB")

    background = fit_background(
        background,
        input_image.size
    )

    result = background.convert("RGBA")

    result.alpha_composite(
        foreground
    )

    return result


# ============================================================
# PROCESS IMAGE
# ============================================================

@app.route("/process", methods=["POST"])
def process_image():

    try:

        if "image" not in request.files:

            return jsonify({
                "success": False,
                "error": "No image was uploaded."
            }), 400

        image_file = request.files["image"]

        if image_file.filename == "":
            return jsonify({
                "success": False,
                "error": "No image was selected."
            }), 400

        option = request.form.get(
            "option",
            ""
        ).strip()

        if not option:

            return jsonify({
                "success": False,
                "error": "No option selected."
            }), 400

        option_number = int(option)

        input_image = Image.open(
            image_file.stream
        ).convert("RGBA")


        # ----------------------------------------------------
        # OPTION 1 - REMOVE BACKGROUND
        # ----------------------------------------------------

        if option_number == 1:

            result = make_background_removal(
                input_image
            )


        # ----------------------------------------------------
        # OPTION 2 - BLUR BACKGROUND
        # ----------------------------------------------------

        elif option_number == 2:

            result = make_blurred_background(
                input_image
            )


        # ----------------------------------------------------
        # OPTION 3+
        # CUSTOM BACKGROUND
        # ----------------------------------------------------

        else:

            img_id = option_number - 2

            filename = find_background_file(
                img_id
            )

            if filename is None:

                return jsonify({
                    "success": False,
                    "error": (
                        "Background image was not found "
                        f"for option {option_number}."
                    )
                }), 404

            background_path = os.path.join(
                BACKGROUND_FOLDER,
                filename
            )

            result = make_custom_background(
                input_image,
                background_path
            )


        # ----------------------------------------------------
        # RETURN IMAGE
        # ----------------------------------------------------

        output = BytesIO()

        # PNG supports transparency.
        result.save(
            output,
            format="PNG"
        )

        output.seek(0)

        return send_file(
            output,
            mimetype="image/png"
        )

    except Exception as e:

        print(
            "\nIMAGE PROCESSING ERROR:"
        )

        print(e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# VOICE COMMAND PROCESSING
# ============================================================

def normalize_command(command):

    command = command.lower().strip()

    # Remove punctuation.
    command = re.sub(
        r"[^\w\s]",
        " ",
        command
    )

    # Remove extra spaces.
    command = re.sub(
        r"\s+",
        " ",
        command
    )

    return command.strip()


def command_to_option(command):

    """
    Convert recognized speech into an option number.

    Examples:

        "remove background" -> 1
        "remove the background" -> 1
        "background removal" -> 1

        "blur background" -> 2
        "blur the background" -> 2

        "use option 3" -> 3
        "option 3" -> 3

        "put me on a mountain"
        -> searches CSV background names
    """

    command = normalize_command(command)


    # --------------------------------------------------------
    # OPTION NUMBER
    # --------------------------------------------------------

    number_match = re.search(
        r"(?:option|background)\s*(\d+)",
        command
    )

    if number_match:

        number = int(
            number_match.group(1)
        )

        if number >= 1:
            return number


    # --------------------------------------------------------
    # REMOVE BACKGROUND
    # --------------------------------------------------------

    remove_phrases = [
        "remove background",
        "remove the background",
        "background removal",
        "remove my background",
        "delete background",
        "delete the background",
        "transparent background",
        "make background transparent"
    ]

    for phrase in remove_phrases:

        if phrase in command:
            return 1


    # --------------------------------------------------------
    # BLUR BACKGROUND
    # --------------------------------------------------------

    blur_phrases = [
        "blur background",
        "blur the background",
        "background blur",
        "blur my background",
        "make background blurry",
        "make the background blurry"
    ]

    for phrase in blur_phrases:

        if phrase in command:
            return 2


    # --------------------------------------------------------
    # MATCH CSV BACKGROUND NAME
    # --------------------------------------------------------

    for record in background_records:

        try:
            img_id = int(
                record.get(
                    "img_id",
                    ""
                ).strip()
            )
        except Exception:
            continue

        name = normalize_command(
            record.get(
                "img_name",
                ""
            )
        )

        if not name:
            continue

        # Exact background name.
        if name == command:
            return img_id + 2

        # Background name appears inside command.
        if name in command:
            return img_id + 2


    return None


# ============================================================
# VOICE ENDPOINT
# ============================================================

@app.route("/voice", methods=["POST"])
def voice_command():

    print()
    print("==============================================")
    print("Listening for voice command...")
    print("==============================================")

    try:

        # ----------------------------------------------------
        # FIND MICROPHONE
        # ----------------------------------------------------

        try:

            microphone = sr.Microphone()

        except Exception as e:

            print("MICROPHONE ERROR:")
            print(e)

            return jsonify({
                "success": False,
                "error": (
                    "Could not access the microphone. "
                    "Check microphone permissions and "
                    "make sure a microphone is connected."
                )
            }), 400


        # ----------------------------------------------------
        # LISTEN
        # ----------------------------------------------------

        with microphone as source:

            print(
                "Adjusting microphone for ambient noise..."
            )

            # Short calibration only.
            recognizer.adjust_for_ambient_noise(
                source,
                duration=0.7
            )

            print(
                "Speak your command now."
            )

            try:

                audio = recognizer.listen(
                    source,
                    timeout=8,
                    phrase_time_limit=8
                )

            except sr.WaitTimeoutError:

                print(
                    "No speech detected."
                )

                return jsonify({
                    "success": False,
                    "error": (
                        "No speech detected. "
                        "Please click the button and speak."
                    )
                }), 400


        # ----------------------------------------------------
        # SPEECH -> TEXT
        # ----------------------------------------------------

        print(
            "Converting speech to text..."
        )

        try:

            command = recognizer.recognize_google(
                audio,
                language="en-US"
            )

        except sr.UnknownValueError:

            print(
                "Speech was heard, but could not "
                "be understood."
            )

            return jsonify({
                "success": False,
                "error": (
                    "Could not understand the speech. "
                    "Please speak clearly and try again."
                )
            }), 400

        except sr.RequestError as e:

            print(
                "Google Speech Recognition request error:"
            )

            print(e)

            return jsonify({
                "success": False,
                "error": (
                    "Speech recognition service could "
                    "not be reached. Check your internet "
                    "connection."
                )
            }), 500


        print(
            "Recognized text:",
            command
        )


        # ----------------------------------------------------
        # TEXT -> COMMAND
        # ----------------------------------------------------

        option = command_to_option(
            command
        )


        if option is None:

            print(
                "Could not map command to an option."
            )

            return jsonify({
                "success": False,
                "text": command,
                "error": (
                    f'Recognized "{command}", '
                    "but could not determine which "
                    "editing option you want."
                )
            }), 400


        print(
            "Selected option:",
            option
        )

        print(
            "Voice command successfully processed."
        )


        return jsonify({
            "success": True,
            "text": command,
            "option": option
        })


    except Exception as e:

        print()
        print(
            "VOICE PROCESSING ERROR:"
        )

        print(e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# ERROR HANDLER
# ============================================================

@app.errorhandler(Exception)
def handle_unexpected_error(error):

    print()
    print(
        "UNEXPECTED SERVER ERROR:"
    )

    print(error)

    return jsonify({
        "success": False,
        "error": str(error)
    }), 500


# ============================================================
# AUTOMATICALLY OPEN BROWSER
# ============================================================

def open_browser():

    webbrowser.open(
        "http://127.0.0.1:5000"
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print()
    print("==============================================")
    print(" Voice Controlled Photo Editor")
    print("==============================================")
    print()

    print(
        "Project directory:"
    )

    print(BASE_DIR)

    print()

    print(
        "CSV:"
    )

    print(CSV_FILE)

    print()

    print(
        "Background folder:"
    )

    print(BACKGROUND_FOLDER)

    print()

    print(
        f"Background records: {len(background_records)}"
    )

    print()

    print(
        "Open:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    print("==============================================")
    print()


    # Open browser after Flask starts.
    threading.Timer(
        1.2,
        open_browser
    ).start()


    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )