import io
import os
import re
import numpy as np
import soundfile as sf
import subprocess  # Added for launching Edge browser
from faster_whisper import WhisperModel
from openai import OpenAI

from utils import ConfigManager

# Dictionary mapping command names to their handler functions
COMMAND_HANDLERS = {}

def register_command(command_phrase):
    """
    Decorator to register command handlers.
    Usage: @register_command("command phrase")
    """
    def decorator(func):
        COMMAND_HANDLERS[command_phrase] = func
        return func
    return decorator

def sanitize_text(text):
    """
    Sanitize text for command detection by removing punctuation, 
    converting to lowercase, and normalizing whitespace.
    """
    # Remove punctuation and convert to lowercase
    sanitized = re.sub(r'[^\w\s]', ' ', text.lower())
    # Normalize whitespace
    sanitized = ' '.join(sanitized.split())
    return sanitized

def create_local_model():
    """
    Create a local model using the faster-whisper library.
    """
    ConfigManager.console_print('Creating local model...')
    local_model_options = ConfigManager.get_config_section('model_options')['local']
    compute_type = local_model_options['compute_type']
    model_path = local_model_options.get('model_path')

    if compute_type == 'int8':
        device = 'cpu'
        ConfigManager.console_print('Using int8 quantization, forcing CPU usage.')
    else:
        device = local_model_options['device']

    try:
        if model_path:
            ConfigManager.console_print(f'Loading model from: {model_path}')
            model = WhisperModel(model_path,
                                 device=device,
                                 compute_type=compute_type,
                                 download_root=None)  # Prevent automatic download
        else:
            model = WhisperModel(local_model_options['model'],
                                 device=device,
                                 compute_type=compute_type)
    except Exception as e:
        ConfigManager.console_print(f'Error initializing WhisperModel: {e}')
        ConfigManager.console_print('Falling back to CPU.')
        model = WhisperModel(model_path or local_model_options['model'],
                             device='cpu',
                             compute_type=compute_type,
                             download_root=None if model_path else None)

    ConfigManager.console_print('Local model created.')
    return model

def transcribe_local(audio_data, local_model=None):
    """
    Transcribe an audio file using a local model.
    """
    if not local_model:
        local_model = create_local_model()
    model_options = ConfigManager.get_config_section('model_options')

    # Convert int16 to float32
    audio_data_float = audio_data.astype(np.float32) / 32768.0

    response = local_model.transcribe(audio=audio_data_float,
                                      language=model_options['common']['language'],
                                      initial_prompt=model_options['common']['initial_prompt'],
                                      condition_on_previous_text=model_options['local']['condition_on_previous_text'],
                                      temperature=model_options['common']['temperature'],
                                      vad_filter=model_options['local']['vad_filter'],)
    return ''.join([segment.text for segment in list(response[0])])

def transcribe_api(audio_data):
    """
    Transcribe an audio file using the OpenAI API.
    """
    model_options = ConfigManager.get_config_section('model_options')
    client = OpenAI(
        api_key=os.getenv('OPENAI_API_KEY') or None,
        base_url=model_options['api']['base_url'] or 'https://api.openai.com/v1'
    )

    # Convert numpy array to WAV file
    byte_io = io.BytesIO()
    sample_rate = ConfigManager.get_config_section('recording_options').get('sample_rate') or 16000
    sf.write(byte_io, audio_data, sample_rate, format='wav')
    byte_io.seek(0)

    response = client.audio.transcriptions.create(
        model=model_options['api']['model'],
        file=('audio.wav', byte_io, 'audio/wav'),
        language=model_options['common']['language'],
        prompt=model_options['common']['initial_prompt'],
        temperature=model_options['common']['temperature'],
    )
    return response.text

# Command handler registration
@register_command("wiz open edge")
def handle_open_edge(transcription):
    """
    Opens Microsoft Edge and brings it to the foreground.
    """
    ConfigManager.console_print("Command detected: Opening Microsoft Edge")
    try:
        # Open Edge and force it to the foreground with /WAIT
        # The /WAIT parameter forces the command to wait for Edge to open before continuing
        subprocess.Popen('start /WAIT microsoft-edge:', shell=True)
        
        # Find and remove the command from the original text
        pattern = re.compile(r'wiz\s+open\s+edge', re.IGNORECASE)
        modified_text = pattern.sub('', transcription)
        
        return True, modified_text.strip()
    except Exception as e:
        ConfigManager.console_print(f"Error executing 'open edge' command: {e}")
        return False, transcription

def execute_commands(transcription):
    """
    Process the transcription text to detect and execute any commands.
    Returns: (bool, str) - (command_executed, modified_transcription)
    """
    # First sanitize the transcription for command detection
    sanitized = sanitize_text(transcription)
    
    # Check for all registered commands
    for command_phrase, handler_func in COMMAND_HANDLERS.items():
        if command_phrase in sanitized:
            # Command found, execute its handler
            return handler_func(transcription)
    
    # No commands were detected
    return False, transcription

def post_process_transcription(transcription):
    """
    Apply post-processing to the transcription.
    """
    transcription = transcription.strip()
    
    # Execute any commands in the transcription
    command_executed, transcription = execute_commands(transcription)
    
    post_processing = ConfigManager.get_config_section('post_processing')
    if post_processing['remove_trailing_period'] and transcription.endswith('.'):
        transcription = transcription[:-1]
    if post_processing['add_trailing_space']:
        transcription += ' '
    if post_processing['remove_capitalization']:
        transcription = transcription.lower()

    return transcription

def transcribe(audio_data, local_model=None):
    """
    Transcribe audio date using the OpenAI API or a local model, depending on config.
    """
    if audio_data is None:
        return ''

    if ConfigManager.get_config_value('model_options', 'use_api'):
        transcription = transcribe_api(audio_data)
    else:
        transcription = transcribe_local(audio_data, local_model)

    return post_process_transcription(transcription)