# Local Text-to-Speech (TTS) Project

This project provides local text-to-speech capabilities using PyTorch.

## Requirements

*   Python 3.8+
*   PyTorch
*   Other dependencies listed in [`requirements.lock.txt`](requirements.lock.txt:1)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/onetapdevai/local_tts.git
    cd <PROJECT_DIRECTORY_NAME>
    ```

2.  **Create and activate a virtual environment using `uv`:**
    ```bash
    uv venv ".local_tts_venv" --python python3.11
    # For Windows
    .local_tts_venv\Scripts\activate
    # For macOS/Linux
    source .local_tts_venv/bin/activate
    ```

3.  **Install PyTorch:**
    Run the [`install_torch.py`](install_torch.py:1) script to install PyTorch according to your system:
    ```bash
    python install_torch.py
    ```
    Alternatively, if you have specific PyTorch version requirements (e.g., for CUDA), install it manually by following the instructions on the [official PyTorch website](https://pytorch.org/get-started/locally/).

4.  **Install other dependencies using `uv`:**
    First, compile the `requirements.in` file into `requirements.lock.txt` (if not already done or if `requirements.in` has been updated):
    ```bash
    uv pip compile requirements.in -o requirements.lock.txt
    ```
    Then, install the dependencies from the generated `requirements.lock.txt`:
    ```bash
    uv pip sync requirements.lock.txt
    ```
    *Note: If you are working only on Windows and [`install.bat`](install.bat:1) performs additional steps specific to your setup, you can continue to use it after installing dependencies via `uv`.*

## Usage

### Running TTS via script

To generate speech from text using the main script [`tts.py`](tts.py:1):
```bash
python tts.py
```
For a full list of arguments and their descriptions, run:
```bash
python tts.py --help
```

### Running the web application (if applicable)

If the project includes a web interface (e.g., using [`app.py`](app.py:1)), run it as follows:
```bash
python app.py
```