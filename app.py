import sys
import os
import datetime
import threading
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QFileDialog, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt, Signal, QObject

# Attempt to import TTS components
try:
    import torch # Added import for torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    TTS_AVAILABLE = True
except ImportError as e:
    print(f"Error importing TTS libraries: {e}. TTS functionality will be disabled.")
    TTS_AVAILABLE = False
    # Define dummy classes/functions if TTS is not available to prevent runtime errors
    class torch: # Added dummy torch class
        @staticmethod
        def cuda():
            return CudaDummy()

    class CudaDummy: # Added dummy CudaDummy class
        @staticmethod
        def is_available():
            return False

    class ChatterboxTTS:
        @staticmethod
        def from_pretrained(device):
            print("TTS Model (dummy) initialized.")
            return None
    
    class ta:
        @staticmethod
        def save(filepath, tensor, sample_rate):
            print(f"Dummy save: {filepath}")
        
        # Removed dummy is_available from ta, as we'll use torch.cuda.is_available

# --- Constants ---
OUTPUT_DIR = "output"
DEFAULT_VOICE_SAMPLE = "your_voice.wav" # Expected in the root directory

# --- TTS Worker ---
class TTSWorker(QObject):
    finished = Signal(str, str) # status_message, output_audio_path
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, text, use_custom_voice, custom_voice_path):
        super().__init__()
        self.text = text
        self.use_custom_voice = use_custom_voice
        self.custom_voice_path = custom_voice_path
        self.model = None

    def load_model(self):
        if not TTS_AVAILABLE:
            self.error.emit("TTS libraries are not available. Please check installation.")
            return False
        try:
            self.progress.emit("Loading TTS model...")
            # Prefer CUDA if available, else CPU
            device = "cuda" if torch.cuda.is_available() else "cpu" # Changed to torch.cuda.is_available()
            self.model = ChatterboxTTS.from_pretrained(device=device)
            self.progress.emit("TTS model loaded successfully.")
            return True
        except Exception as e:
            self.error.emit(f"Error loading TTS model: {e}")
            self.model = None
            return False

    def run(self):
        if not self.load_model():
            return

        if not self.model:
            self.error.emit("TTS model not loaded.")
            return

        if not self.text or self.text.strip() == "":
            self.error.emit("Please enter some text to synthesize.")
            return

        try:
            self.progress.emit("Generating speech...")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"speech_{timestamp}"
            
            audio_prompt_to_use = None
            if self.use_custom_voice:
                if self.custom_voice_path and os.path.exists(self.custom_voice_path):
                    audio_prompt_to_use = self.custom_voice_path
                    filename_base += "_custom_voice"
                    self.progress.emit(f"Using custom voice: {os.path.basename(self.custom_voice_path)}")
                elif os.path.exists(DEFAULT_VOICE_SAMPLE):
                    audio_prompt_to_use = DEFAULT_VOICE_SAMPLE
                    filename_base += "_default_custom_voice"
                    self.progress.emit(f"Custom voice not provided or invalid. Using default: {DEFAULT_VOICE_SAMPLE}")
                else:
                    self.error.emit(f"Custom voice selected, but '{os.path.basename(self.custom_voice_path) if self.custom_voice_path else 'no file'}' not found and default '{DEFAULT_VOICE_SAMPLE}' also not found.")
                    return
            else:
                self.progress.emit("Using standard voice.")

            self.progress.emit(f"Synthesizing: '{self.text[:50]}...'")
            wav = self.model.generate(self.text, audio_prompt_path=audio_prompt_to_use)
            
            output_filename = f"{filename_base}.wav"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            
            # Ensure output directory exists
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)
                self.progress.emit(f"Created output directory: {OUTPUT_DIR}")

            ta.save(output_path, wav, self.model.sr)
            self.progress.emit(f"Speech saved to: {output_path}")
            self.finished.emit(f"Speech generated: {output_filename}", output_path)

        except Exception as e:
            self.error.emit(f"Error during speech generation: {e}")

# --- Main Application Window ---
class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Text-to-Speech Application")
        self.setGeometry(100, 100, 600, 400)
        
        self.current_audio_file = None
        self.tts_thread = None
        self.worker = None

        self._init_ui()

        if not TTS_AVAILABLE:
            self.status_text.setText("TTS libraries not found. Please install them (chatterbox-tts, torchaudio).")
            self.generate_button.setEnabled(False)


    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # Text Input
        self.text_input_label = QLabel("Enter Text:")
        main_layout.addWidget(self.text_input_label)
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Type your text here...")
        main_layout.addWidget(self.text_input)

        # Custom Voice Options
        custom_voice_layout = QHBoxLayout()
        self.use_custom_voice_checkbox = QCheckBox("Use Custom Voice Sample")
        self.use_custom_voice_checkbox.toggled.connect(self._toggle_custom_voice_ui)
        custom_voice_layout.addWidget(self.use_custom_voice_checkbox)

        self.custom_voice_path_edit = QLineEdit()
        self.custom_voice_path_edit.setPlaceholderText("Path to .wav file")
        self.custom_voice_path_edit.setEnabled(False)
        custom_voice_layout.addWidget(self.custom_voice_path_edit)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_for_voice_sample)
        self.browse_button.setEnabled(False)
        custom_voice_layout.addWidget(self.browse_button)
        main_layout.addLayout(custom_voice_layout)

        # Generate Button
        self.generate_button = QPushButton("Generate Speech")
        self.generate_button.clicked.connect(self._start_tts_generation)
        main_layout.addWidget(self.generate_button)

        # Play Button
        self.play_button = QPushButton("Play Last Generated Audio")
        self.play_button.clicked.connect(self._play_last_audio)
        self.play_button.setEnabled(False) # Initially disabled
        main_layout.addWidget(self.play_button)

        # Status/Output
        self.status_label = QLabel("Status:")
        main_layout.addWidget(self.status_label)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFixedHeight(100)
        main_layout.addWidget(self.status_text)
        
        # Info
        info_label = QLabel(f"Generated audio will be saved in '{OUTPUT_DIR}'.\nIf 'Use Custom Voice' is checked and no file is selected, it will try to use '{DEFAULT_VOICE_SAMPLE}'.")
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

    def _play_last_audio(self):
        if self.current_audio_file and os.path.exists(self.current_audio_file):
            try:
                if sys.platform == "win32":
                    os.startfile(self.current_audio_file)
                elif sys.platform == "darwin": # macOS
                    subprocess.call(["open", self.current_audio_file])
                else: # Linux and other Unix-like
                    subprocess.call(["xdg-open", self.current_audio_file])
                self.status_text.append(f"Attempting to play: {self.current_audio_file}")
            except Exception as e:
                self.status_text.append(f"Error playing audio: {e}")
                QMessageBox.warning(self, "Playback Error", f"Could not play audio file: {e}")
        else:
            self.status_text.append("No audio file to play or file not found.")
            QMessageBox.information(self, "Playback Info", "No audio has been generated yet, or the file is missing.")

    def _toggle_custom_voice_ui(self, checked):
        self.custom_voice_path_edit.setEnabled(checked)
        self.browse_button.setEnabled(checked)
        if not checked:
            self.custom_voice_path_edit.clear()

    def _browse_for_voice_sample(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Custom Voice Sample", "", "WAV Files (*.wav)")
        if file_path:
            self.custom_voice_path_edit.setText(file_path)

    def _start_tts_generation(self):
        text = self.text_input.toPlainText()
        use_custom = self.use_custom_voice_checkbox.isChecked()
        custom_voice_file = self.custom_voice_path_edit.text()

        if not text.strip():
            QMessageBox.warning(self, "Input Error", "Please enter some text to synthesize.")
            return

        if use_custom and not custom_voice_file and not os.path.exists(DEFAULT_VOICE_SAMPLE):
             QMessageBox.warning(self, "Input Error", f"Custom voice is selected, but no file is provided and '{DEFAULT_VOICE_SAMPLE}' was not found.")
             return
        
        self.generate_button.setEnabled(False)
        self.status_text.clear()
        self.status_text.append("Starting generation...")

        # Create and start worker thread
        self.worker = TTSWorker(text, use_custom, custom_voice_file if use_custom else None)
        self.tts_thread = threading.Thread(target=self.worker.run, daemon=True) # Use threading.Thread for simplicity with QObject signals
        
        # Connect signals from worker
        # Note: For proper Qt thread integration, QThread and moveToThread is preferred,
        # but for this simple case, basic threading with signals can work if worker emits signals correctly.
        # For robustness, especially with GUI updates from threads, QThread is better.
        # However, let's try with threading.Thread first for simplicity.
        # A QProgressDialog might be better for long operations.
        
        # For direct GUI updates from a non-GUI thread, it's safer to use signals.
        # Let's refine this part if direct threading causes issues.
        # The worker itself is a QObject, so its signals should be thread-safe.

        self.worker.finished.connect(self._on_tts_finished)
        self.worker.error.connect(self._on_tts_error)
        self.worker.progress.connect(self._update_status)
        
        self.tts_thread.start()

    def _update_status(self, message):
        self.status_text.append(message)

    def _on_tts_finished(self, status_message, output_audio_path):
        self.status_text.append(f"Success: {status_message}")
        self.status_text.append(f"Output file: {output_audio_path}")
        self.current_audio_file = output_audio_path
        self.generate_button.setEnabled(True)
        self.play_button.setEnabled(True) # Enable play button
        QMessageBox.information(self, "TTS Complete", f"{status_message}\nSaved to: {output_audio_path}")
        # We don't have a built-in player, so just notify.

    def _on_tts_error(self, error_message):
        self.status_text.append(f"Error: {error_message}")
        self.generate_button.setEnabled(True)
        self.play_button.setEnabled(False) # Keep play button disabled on error
        QMessageBox.critical(self, "TTS Error", error_message)

    def closeEvent(self, event):
        # Clean up thread if running
        if self.tts_thread and self.tts_thread.is_alive():
            # QThread has quit() and wait(). For threading.Thread, it's harder to stop cleanly.
            # Since it's a daemon, it should exit when the main app exits.
            # For a more graceful shutdown, worker would need a stop flag.
            print("TTS thread is still running. Closing app.")
        event.accept()


# --- Main Execution ---
if __name__ == "__main__":
    # Create output directory if it doesn't exist, before app starts
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"Output directory '{OUTPUT_DIR}' created.")
        except OSError as e:
            print(f"Error creating output directory '{OUTPUT_DIR}': {e}")
            # Proceed, but generation might fail if dir cannot be made by worker

    app = QApplication(sys.argv)
    main_window = TTSApp()
    main_window.show()
    sys.exit(app.exec())