# kokoro_tts_api
A simple TTS API for kokoro cli on Windows.


**Purpose:**

The script implements a Flask-based REST API server that acts as a wrapper for the `kokoro` command-line text-to-speech (TTS) tool. It provides endpoints to convert text into speech using various available voices and returns the audio in WAV format.

**Key Components and Functionality:**

1.  **Flask Application (`app`)**: The core web server framework used to define routes and handle HTTP requests/responses.
2.  **Configuration (`Config` class)**:
    *   `MAX_TEXT_LENGTH`: Limits input text length (10,000 chars) to prevent resource abuse.
    *   `ALLOWED_VOICES`: A predefined list of voice identifiers that the API accepts.
    *   `TEMP_DIR`: Specifies the directory (`./output_temp`) for storing temporary audio files during synthesis.
    *   `CLEANUP_FILES`: A flag (default `True`) to control whether temporary files are deleted after being sent to the client.
3.  **Initialization (`if __name__ == '__main__'` block)**:
    *   Calls `ensure_temp_directory()` to create the temp directory if needed and verify write permissions.
    *   Checks if the `kokoro` command-line tool is installed and accessible by running `kokoro --help`.
    *   Starts the Flask development server on `0.0.0.0:9880` with threading enabled.
4.  **Helper Functions:**
    *   `ensure_temp_directory()`: Ensures the temporary directory exists and is writable.
    *   `validate_request_data(data)`: Parses and validates the JSON payload from POST requests. Checks for required `text`, enforces length limits, validates the `voice` against `ALLOWED_VOICES`, and ensures no unsupported `format` is requested (only WAV is supported).
    *   `run_kokoro_command(text, voice, output_path)`: Executes the external `kokoro` command using `subprocess.run`. It constructs the command with the provided text, voice, and output path, runs it with a 60-second timeout, and checks for success (return code 0) and file creation.
5.  **API Endpoints:**
    *   `/health` (GET): Returns a JSON status message indicating the API is running.
    *   `/voices` (GET): Returns a JSON list of available voices and the default voice.
    *   `/synthesize` (POST): The main synthesis endpoint. Accepts JSON with `text` and optional `voice`. It validates the input, runs `kokoro`, saves the output to a temporary `.wav` file, and uses `send_file` to return the file as an attachment. It employs a `call_on_close` hook to clean up the temporary file after the response is sent.
    *   `/synthesize/stream` (POST): A streaming variant of `/synthesize`. It performs the same validation and synthesis steps but reads the generated WAV file into memory and returns the raw bytes directly in the response body, setting appropriate headers (`Content-Type`, `Content-Disposition`). It cleans up the temporary file immediately after reading.
6.  **Error Handling:**
    *   Uses `try...except` blocks within endpoints to catch `BadRequest` (from validation) and general `Exception`.
    *   Returns appropriate JSON error responses with HTTP status codes (400 for bad requests, 500 for internal errors).
    *   Includes specific error handlers for common HTTP errors like 404 (Not Found) and 405 (Method Not Allowed).
7.  **Logging:** Uses Python's `logging` module (configured for INFO level) to log significant events like directory creation, command execution, errors, and file cleanup.

**How to use:**
1.  **Activate python venv:**
    *   python -m venv venv
    *   call venv\Scripts\activate
    *   Using uv works too
2.  **Install kokoro:**
    *   git clone https://github.com/hexgrad/kokoro.git
    *   cd kokoro
    *   pip install -e .
3.  **Run kokoro_tts_api:**
    *   install required modules (pip install <missing_module>)
    *   python kokoro_tts_api.py
    *   optional, install pytorch cuda for gpu mode support
4.  **Inference test:**
    *   Edit text and voice in "request.json"
    *   Run "inference.bat"
    *   If success the result will be in wav format "output.wav" and in "output_temp" folder
5.  **Accessing the API:**
    *   KOKORO_TTS_URL = "http://localhost:9880/synthesize/stream"
