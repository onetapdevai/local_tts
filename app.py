import sys
import os
import datetime
import threading
import subprocess # Added for playing audio
import math # For duration formatting
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QFileDialog, QMessageBox, QProgressDialog, QSlider, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
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

        @staticmethod
        def info(filepath):
            print(f"Dummy torchaudio.info called for {filepath}")
            # Return a dummy object that mimics the structure needed for duration calculation
            class DummyInfo:
                def __init__(self):
                    self.num_frames = 0
                    self.sample_rate = 16000 # Dummy sample rate
            return DummyInfo()
        
        # Removed dummy is_available from ta, as we'll use torch.cuda.is_available

# --- Constants ---
OUTPUT_DIR = "output"
DEFAULT_VOICE_SAMPLE = "your_voice.wav" # Expected in the root directory

# --- TTS Worker ---
class TTSWorker(QObject):
    finished = Signal(str, str) # status_message, output_audio_path
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, text, use_custom_voice, custom_voice_path, exaggeration, temperature, cfg_weight):
        super().__init__()
        self.text = text
        self.use_custom_voice = use_custom_voice
        self.custom_voice_path = custom_voice_path
        self.exaggeration = exaggeration
        self.temperature = temperature
        self.cfg_weight = cfg_weight
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

            self.progress.emit(f"Synthesizing: '{self.text[:50]}...' with Exaggeration: {self.exaggeration}, Temp: {self.temperature}, CFG: {self.cfg_weight}")
            wav = self.model.generate(
                self.text,
                audio_prompt_path=audio_prompt_to_use,
                exaggeration=self.exaggeration,
                temperature=self.temperature,
                cfg_weight=self.cfg_weight
            )
            
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
        self.generated_audio_files = [] # To store info about generated files

        self._init_ui()
        self._load_existing_audio_files() # Load existing files on startup

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

        # Generation Parameters
        params_groupbox = QGroupBox("Generation Parameters")
        params_layout = QVBoxLayout()

        # Exaggeration
        self.exaggeration_label = QLabel(f"Exaggeration: {0.5:.2f} (Neutral = 0.5)")
        params_layout.addWidget(self.exaggeration_label)
        self.exaggeration_slider = QSlider(Qt.Horizontal)
        self.exaggeration_slider.setRange(25, 200) # 0.25 to 2.00, step 0.05
        self.exaggeration_slider.setValue(50) # Default 0.50
        self.exaggeration_slider.setSingleStep(5)
        self.exaggeration_slider.setTickInterval(25) # Tick for 0.25 steps
        self.exaggeration_slider.setTickPosition(QSlider.TicksBelow)
        self.exaggeration_slider.valueChanged.connect(lambda value: self.exaggeration_label.setText(f"Exaggeration: {value / 100:.2f} (Neutral = 0.5)"))
        params_layout.addWidget(self.exaggeration_slider)

        # Temperature
        self.temperature_label = QLabel(f"Temperature: {0.8:.2f}")
        params_layout.addWidget(self.temperature_label)
        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setRange(5, 500) # 0.05 to 5.00, step 0.05
        self.temperature_slider.setValue(80) # Default 0.80
        self.temperature_slider.setSingleStep(5)
        self.temperature_slider.setTickInterval(50) # Tick for 0.5 steps
        self.temperature_slider.setTickPosition(QSlider.TicksBelow)
        self.temperature_slider.valueChanged.connect(lambda value: self.temperature_label.setText(f"Temperature: {value / 100:.2f}"))
        params_layout.addWidget(self.temperature_slider)

        # CFG Weight
        self.cfg_weight_label = QLabel(f"CFG Weight/Pace: {0.5:.2f}")
        params_layout.addWidget(self.cfg_weight_label)
        self.cfg_weight_slider = QSlider(Qt.Horizontal)
        self.cfg_weight_slider.setRange(20, 100) # 0.20 to 1.00, step 0.05
        self.cfg_weight_slider.setValue(50) # Default 0.50
        self.cfg_weight_slider.setSingleStep(5)
        self.cfg_weight_slider.setTickInterval(10) # Tick for 0.1 steps
        self.cfg_weight_slider.setTickPosition(QSlider.TicksBelow)
        self.cfg_weight_slider.valueChanged.connect(lambda value: self.cfg_weight_label.setText(f"CFG Weight/Pace: {value / 100:.2f}"))
        params_layout.addWidget(self.cfg_weight_slider)
        
        params_groupbox.setLayout(params_layout)
        main_layout.addWidget(params_groupbox)

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

        # Generated Audio List
        audio_list_groupbox = QGroupBox("Generated Audio Files")
        audio_list_layout = QVBoxLayout()

        self.audio_table = QTableWidget()
        self.audio_table.setColumnCount(4) # Filename, Duration, Play, Delete
        self.audio_table.setHorizontalHeaderLabels(["File", "Duration", "Play", "Delete"])
        self.audio_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch) # Filename
        self.audio_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents) # Duration
        self.audio_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # Play
        self.audio_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents) # Delete
        self.audio_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.audio_table.setEditTriggers(QAbstractItemView.NoEditTriggers) # Make table read-only
        self.audio_table.setFixedHeight(150) # Adjust as needed
        audio_list_layout.addWidget(self.audio_table)
        
        audio_list_groupbox.setLayout(audio_list_layout)
        main_layout.addWidget(audio_list_groupbox)

    def _play_last_audio(self): # This button might become redundant or act on the latest in the list
        if self.generated_audio_files:
            # Play the most recently added file
            audio_to_play = self.generated_audio_files[-1]["path"]
            if os.path.exists(audio_to_play):
                self._play_audio_file(audio_to_play)
            else:
                self.status_text.append(f"Error: File {audio_to_play} not found.")
                QMessageBox.warning(self, "Playback Error", f"File not found: {audio_to_play}")
        elif self.current_audio_file and os.path.exists(self.current_audio_file): # Fallback for older logic if needed
             self._play_audio_file(self.current_audio_file)
        else:
            self.status_text.append("No audio file to play or file not found.")
            QMessageBox.information(self, "Playback Info", "No audio has been generated yet, or the file is missing.")

    def _play_audio_file(self, file_path):
        if file_path and os.path.exists(file_path):
            try:
                if sys.platform == "win32":
                    os.startfile(file_path)
                elif sys.platform == "darwin": # macOS
                    subprocess.call(["open", file_path])
                else: # Linux and other Unix-like
                    subprocess.call(["xdg-open", file_path])
                self.status_text.append(f"Attempting to play: {file_path}")
            except Exception as e:
                self.status_text.append(f"Error playing audio: {e}")
                QMessageBox.warning(self, "Playback Error", f"Could not play audio file: {e}")

    def _update_audio_list_table(self):
        self.audio_table.setRowCount(0) # Clear existing rows
        for idx, audio_info in enumerate(self.generated_audio_files):
            self.audio_table.insertRow(idx)
            self.audio_table.setItem(idx, 0, QTableWidgetItem(audio_info["name"]))
            self.audio_table.setItem(idx, 1, QTableWidgetItem(audio_info["duration_str"]))
            
            play_button = QPushButton("Play")
            play_button.clicked.connect(lambda checked=False, path=audio_info["path"]: self._play_audio_file(path))
            self.audio_table.setCellWidget(idx, 2, play_button)

            delete_button = QPushButton("Delete")
            delete_button.clicked.connect(lambda checked=False, path=audio_info["path"], row_idx=idx: self._delete_audio_file_from_list(path, row_idx)) # Pass idx for removal from model
            self.audio_table.setCellWidget(idx, 3, delete_button)
        # self.audio_table.resizeColumnsToContents() # Adjust column sizes after populating - Removed to prevent shrinking


    def _delete_audio_file_from_list(self, file_path, row_idx_in_model_hint):
        # Find the actual index in self.generated_audio_files based on path,
        # as row_idx_in_model_hint from the lambda might become stale if items are deleted rapidly
        # or if the list is modified elsewhere. A more robust way is to find by unique ID or path.
        actual_idx_to_delete = -1
        for i, audio_file_info in enumerate(self.generated_audio_files):
            if audio_file_info["path"] == file_path:
                actual_idx_to_delete = i
                break
        
        if actual_idx_to_delete != -1:
            confirm_delete = QMessageBox.question(self, "Confirm Delete",
                                                  f"Are you sure you want to delete '{os.path.basename(file_path)}'?",
                                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if confirm_delete == QMessageBox.Yes:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        self.status_text.append(f"Deleted file from disk: {file_path}")
                    
                    del self.generated_audio_files[actual_idx_to_delete]
                    self.status_text.append(f"Removed '{os.path.basename(file_path)}' from list.")
                    self._update_audio_list_table() # Refresh the table
                    
                except Exception as e:
                    self.status_text.append(f"Error deleting file {file_path}: {e}")
                    QMessageBox.warning(self, "Delete Error", f"Could not delete file: {e}")
        else:
            self.status_text.append(f"File {file_path} not found in internal list for deletion. Refreshing list.")
            self._update_audio_list_table() # Refresh table in case of mismatch

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

        exaggeration_val = self.exaggeration_slider.value() / 100.0
        temperature_val = self.temperature_slider.value() / 100.0
        cfg_weight_val = self.cfg_weight_slider.value() / 100.0

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
        self.worker = TTSWorker(text, use_custom, custom_voice_file if use_custom else None,
                                exaggeration_val, temperature_val, cfg_weight_val)
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
        self.current_audio_file = output_audio_path # Keep for "Play Last Generated" if still desired
        
        duration_str = "N/A"
        if TTS_AVAILABLE and hasattr(ta, 'info'): # Check if torchaudio.info is available
            try:
                audio_info = ta.info(output_audio_path)
                if audio_info.num_frames > 0 and audio_info.sample_rate > 0:
                    duration_seconds = audio_info.num_frames / audio_info.sample_rate
                    minutes = math.floor(duration_seconds / 60)
                    seconds = math.floor(duration_seconds % 60)
                    duration_str = f"{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = "00:00" # Or some other indicator of empty/invalid audio
            except Exception as e:
                self.status_text.append(f"Could not get audio duration for {output_audio_path}: {e}")
                print(f"Error getting duration for {output_audio_path}: {e}")

        self.generated_audio_files.append({
            "path": output_audio_path,
            "name": os.path.basename(output_audio_path),
            "duration_str": duration_str
        })
        # Keep the list to a reasonable size, e.g., last 10-20 items
        MAX_AUDIO_LIST_SIZE = 20
        if len(self.generated_audio_files) > MAX_AUDIO_LIST_SIZE:
            # Potentially remove oldest files from disk too if they are not referenced elsewhere
            # For now, just remove from the list in UI
            self.generated_audio_files = self.generated_audio_files[-MAX_AUDIO_LIST_SIZE:]

        self._update_audio_list_table()

        self.generate_button.setEnabled(True)
        self.play_button.setEnabled(True) # Enable "Play Last Generated" button
        QMessageBox.information(self, "TTS Complete", f"{status_message}\nSaved to: {output_audio_path}")

    def _load_existing_audio_files(self):
        if not os.path.exists(OUTPUT_DIR):
            # Create output directory if it doesn't exist, similar to __main__
            try:
                os.makedirs(OUTPUT_DIR)
                self.status_text.append(f"Output directory '{OUTPUT_DIR}' created during startup check.")
                print(f"Output directory '{OUTPUT_DIR}' created during startup check.")
            except OSError as e:
                self.status_text.append(f"Error creating output directory '{OUTPUT_DIR}' on startup: {e}")
                print(f"Error creating output directory '{OUTPUT_DIR}' on startup: {e}")
                return # Cannot proceed if dir creation fails here

        found_files_with_details = []
        try:
            for filename in os.listdir(OUTPUT_DIR):
                if filename.lower().endswith(".wav"):
                    file_path = os.path.join(OUTPUT_DIR, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        duration_str = "N/A"
                        # Ensure ta and ta.info are valid before calling
                        if TTS_AVAILABLE and hasattr(ta, 'info') and callable(getattr(ta, 'info', None)):
                            audio_info = ta.info(file_path)
                            if audio_info.num_frames > 0 and audio_info.sample_rate > 0:
                                duration_seconds = audio_info.num_frames / audio_info.sample_rate
                                minutes = math.floor(duration_seconds / 60)
                                seconds = math.floor(duration_seconds % 60)
                                duration_str = f"{minutes:02d}:{seconds:02d}"
                            else:
                                duration_str = "00:00" # File might be empty or corrupt
                        else:
                             # Fallback if TTS_AVAILABLE is False or ta.info is not proper
                            duration_str = "N/A (info unavailable)"

                        found_files_with_details.append({
                            "path": file_path,
                            "name": filename,
                            "duration_str": duration_str,
                            "mtime": mtime
                        })
                    except Exception as e:
                        print(f"Error processing existing file {file_path}: {e}")
                        # self.status_text.append(f"Couldn't process existing file {filename}: {e}") # Avoid too much noise on status for minor issues
            
            # Sort files by modification time, newest first
            found_files_with_details.sort(key=lambda x: x["mtime"], reverse=True)
            
            MAX_AUDIO_LIST_SIZE = 20
            self.generated_audio_files = found_files_with_details[:MAX_AUDIO_LIST_SIZE]
            
            if self.generated_audio_files:
                 self.status_text.append(f"Loaded {len(self.generated_audio_files)} existing audio file(s) from '{OUTPUT_DIR}'.")
            else:
                self.status_text.append(f"No existing .wav files found in '{OUTPUT_DIR}'.")

            self._update_audio_list_table()

        except Exception as e:
            print(f"Error loading existing audio files: {e}")
            self.status_text.append(f"Error loading existing audio files: {e}")
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