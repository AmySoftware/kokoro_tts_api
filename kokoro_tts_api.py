#!/usr/bin/env python3
"""
Kokoro TTS API Server

A Flask-based REST API wrapper for the Kokoro TTS command-line tool.
Provides endpoints for text-to-speech conversion with various voice options.
"""

import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''   # CPU = '-1', GPU = ''
import subprocess
import tempfile
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort
from werkzeug.exceptions import BadRequest
import logging
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
class Config:
    MAX_TEXT_LENGTH = 10000  # Maximum text length to prevent abuse
    ALLOWED_VOICES = [
        'af_alloy', 'af_aoede', 'af_bella', 'af_heart', 'af_jessica', 'af_kore', 
        'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky', 'am_adam', 
        'am_michael', 'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily', 
        'bm_george', 'bm_lewis', 'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 
        'jf_tebukuro'
    ]  # Add more voices as needed
    TEMP_DIR = os.path.join(os.getcwd(), "output_temp")  # Current working directory + output_temp
    CLEANUP_FILES = True  # Set to False for debugging

config = Config()

# Create the output_temp directory if it doesn't exist
def ensure_temp_directory():
    """Ensure the temp directory exists and is writable."""
    try:
        if not os.path.exists(config.TEMP_DIR):
            os.makedirs(config.TEMP_DIR)
            logger.info(f"Created temp directory: {config.TEMP_DIR}")
        else:
            logger.info(f"Using existing temp directory: {config.TEMP_DIR}")
        
        # Test if directory is writable
        test_file = os.path.join(config.TEMP_DIR, "test_write.tmp")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        
    except Exception as e:
        logger.error(f"Failed to create or access temp directory {config.TEMP_DIR}: {e}")
        raise

def validate_request_data(data: Dict[str, Any]) -> tuple[str, str]:
    """
    Validate incoming request data.
    
    Returns:
        tuple: (text, voice)
    
    Raises:
        BadRequest: If validation fails
    """
    if not data:
        raise BadRequest("Request body is required")
    
    text = data.get('text', '').strip()
    if not text:
        raise BadRequest("Text field is required and cannot be empty")
    
    if len(text) > config.MAX_TEXT_LENGTH:
        raise BadRequest(f"Text length exceeds maximum of {config.MAX_TEXT_LENGTH} characters")
    
    voice = data.get('voice', 'af_heart')
    if voice not in config.ALLOWED_VOICES:
        raise BadRequest(f"Invalid voice. Allowed voices: {', '.join(config.ALLOWED_VOICES)}")
    
    # Remove format validation since we only support WAV
    format_param = data.get('format')
    if format_param and format_param.lower() != 'wav':
        raise BadRequest("Only WAV format is supported. Please omit the format parameter or use 'wav'.")
    
    return text, voice

def run_kokoro_command(text: str, voice: str, output_path: str) -> bool:
    """
    Execute the kokoro TTS command.
    
    Args:
        text: Text to synthesize
        voice: Voice to use
        output_path: Output file path
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        cmd = [
            'kokoro',
            '--voice', voice,
            '--text', text,
            '-o', output_path
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Kokoro command failed: {result.stderr}")
            return False
            
        if not os.path.exists(output_path):
            logger.error(f"Output file was not created: {output_path}")
            return False
            
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Kokoro command timed out")
        return False
    except Exception as e:
        logger.error(f"Error running kokoro command: {e}")
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Kokoro TTS API',
        'version': '1.0.0',
        'supported_format': 'wav'
    })

@app.route('/voices', methods=['GET'])
def get_voices():
    """Get list of available voices."""
    return jsonify({
        'voices': config.ALLOWED_VOICES,
        'default': 'af_heart',
        'supported_format': 'wav'
    })

@app.route('/synthesize', methods=['POST'])
def synthesize_text():
    """
    Main TTS synthesis endpoint.
    
    Expected JSON payload:
    {
        "text": "Text to synthesize",
        "voice": "af_heart"  // optional, defaults to af_heart
    }
    
    Note: Only WAV format is supported.
    """
    try:
        # Parse and validate request
        data = request.get_json()
        text, voice = validate_request_data(data)
        
        # Generate unique filename (always WAV)
        file_id = str(uuid.uuid4())
        output_filename = f"kokoro_tts_{file_id}.wav"
        output_path = os.path.join(config.TEMP_DIR, output_filename)
        
        # Run Kokoro TTS
        success = run_kokoro_command(text, voice, output_path)
        
        if not success:
            return jsonify({
                'error': 'TTS synthesis failed',
                'message': 'Failed to generate audio file'
            }), 500
        
        # Return the audio file
        def remove_file(response):
            """Clean up temporary file after sending."""
            if config.CLEANUP_FILES:
                try:
                    os.unlink(output_path)
                    logger.info(f"Cleaned up temporary file: {output_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up file {output_path}: {e}")
            return response
        
        response = send_file(
            output_path,
            as_attachment=True,
            download_name="tts_output.wav",
            mimetype='audio/wav'
        )
        
        response.call_on_close(remove_file)
        return response
        
    except BadRequest as e:
        return jsonify({'error': 'Invalid request', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in synthesize_text: {e}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500

@app.route('/synthesize/stream', methods=['POST'])
def synthesize_stream():
    """
    Streaming TTS synthesis endpoint that returns WAV audio data directly.
    """
    try:
        data = request.get_json()
        text, voice = validate_request_data(data)
        
        # Generate unique filename (always WAV)
        file_id = str(uuid.uuid4())
        output_filename = f"kokoro_tts_{file_id}.wav"
        output_path = os.path.join(config.TEMP_DIR, output_filename)
        
        # Run Kokoro TTS
        success = run_kokoro_command(text, voice, output_path)
        
        if not success:
            return jsonify({
                'error': 'TTS synthesis failed',
                'message': 'Failed to generate audio file'
            }), 500
        
        # Read file and return as bytes
        try:
            with open(output_path, 'rb') as f:
                audio_data = f.read()
            
            # Clean up immediately
            if config.CLEANUP_FILES:
                os.unlink(output_path)
            
            return audio_data, 200, {
                'Content-Type': 'audio/wav',
                'Content-Disposition': 'inline; filename="tts_output.wav"'
            }
            
        except Exception as e:
            logger.error(f"Error reading output file: {e}")
            return jsonify({
                'error': 'File read error',
                'message': 'Failed to read generated audio file'
            }), 500
        
    except BadRequest as e:
        return jsonify({'error': 'Invalid request', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in synthesize_stream: {e}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not found',
        'message': 'The requested endpoint does not exist'
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'error': 'Method not allowed',
        'message': 'The HTTP method is not allowed for this endpoint'
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500

if __name__ == '__main__':
    # Ensure temp directory exists
    ensure_temp_directory()

    # Check if kokoro is available
    try:
        result = subprocess.run(['kokoro', '--help'], capture_output=True, timeout=10)
        if result.returncode != 0:
            logger.error("Kokoro command not found or not working properly")
            exit(1)
    except Exception as e:
        logger.error(f"Failed to verify kokoro installation: {e}")
        exit(1)
    
    logger.info("Starting Kokoro TTS API Server...")
    logger.info(f"Available voices: {', '.join(config.ALLOWED_VOICES)}")
    logger.info(f"Using temp directory: {config.TEMP_DIR}")
    logger.info("Supported format: WAV only")
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=9880,
        debug=False,  # Set to True for development
        threaded=True
    )