import subprocess
import sys
import logging
from typing import Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_cuda_toolkit_version_str() -> Optional[str]:
    """
    Detects the installed CUDA toolkit version.
    Returns the version string (e.g., "118" for CUDA 11.8) or None if not found.
    """
    try:
        # Attempt to get CUDA version using nvcc
        process_output = subprocess.check_output(
            ["nvcc", "--version"],
            text=True,
            stderr=subprocess.PIPE  # Capture stderr to check for errors silently
        )
        for line in process_output.splitlines():
            if "release" in line.lower(): # Make search case-insensitive
                # Example line: "Cuda compilation tools, release 11.8, V11.8.89"
                version_part = line.lower().split("release")[-1].strip()
                version_number_str = version_part.split(",")[0].strip() # "11.8"
                # Remove dot and return, e.g., "118"
                return version_number_str.replace(".", "")
    except FileNotFoundError:
        logger.debug("nvcc command not found. CUDA toolkit might not be installed or not in PATH.")
    except subprocess.CalledProcessError as e:
        logger.debug(f"nvcc --version command failed with error: {e.stderr}")
    except Exception as e:
        logger.warning(f"An unexpected error occurred while detecting CUDA version: {e}")
    return None

def determine_pytorch_index_url(cuda_version_str: Optional[str]) -> str:
    """
    Determines the appropriate PyTorch wheel index URL based on the CUDA version.
    Falls back to CPU if CUDA version is not provided.
    """
    if cuda_version_str:
        # Construct URL for CUDA-enabled PyTorch
        # e.g., https://download.pytorch.org/whl/cu118
        return f"https://download.pytorch.org/whl/cu{cuda_version_str}"
    else:
        # Fallback to CPU-only PyTorch
        logger.info("CUDA not detected or version unknown, defaulting to CPU PyTorch index.")
        return "https://download.pytorch.org/whl/cpu"

def execute_pytorch_installation(pytorch_index_url: str, packages: List[str] = None) -> None:
    """
    Installs PyTorch, torchvision, and torchaudio using 'uv pip install'.
    """
    if packages is None:
        packages = ["torch", "torchvision", "torchaudio"]

    logger.info(f"Attempting to install {', '.join(packages)} using index: {pytorch_index_url}")
    
    installation_command: List[str] = [
        "uv", "pip", "install",
        *packages,
        "--index-url", pytorch_index_url
    ]

    # Add --pre flag if installing from a nightly build URL (heuristic)
    if "nightly" in pytorch_index_url or "test" in pytorch_index_url:
        logger.info("Nightly or test URL detected, adding --pre flag for pip.")
        installation_command.append("--pre")
    
    try:
        logger.info(f"Executing command: {' '.join(installation_command)}")
        subprocess.run(installation_command, check=True, text=True, capture_output=True)
        logger.info(f"{', '.join(packages)} installed successfully from {pytorch_index_url}.")
    except subprocess.CalledProcessError as e:
        logger.error(f"PyTorch installation failed with return code {e.returncode}.")
        logger.error(f"Command: {' '.join(e.cmd)}")
        if e.stdout:
            logger.error(f"Stdout:\n{e.stdout}")
        if e.stderr:
            logger.error(f"Stderr:\n{e.stderr}")
        logger.error("Please try installing manually or check the 'uv' and network configuration.")
        sys.exit(1)
    except FileNotFoundError:
        logger.error("'uv' command not found. Please ensure 'uv' is installed and in your PATH.")
        logger.error("You can install 'uv' from https://github.com/astral-sh/uv")
        sys.exit(1)

def main() -> None:
    """
    Main script execution function.
    """
    logger.info("Starting PyTorch installation script.")
    
    cuda_version = get_cuda_toolkit_version_str()
    if cuda_version:
        logger.info(f"Detected CUDA toolkit version: {cuda_version} (formatted as cu{cuda_version})")
    else:
        logger.info("No CUDA toolkit detected or version could not be determined.")
        
    pytorch_url = determine_pytorch_index_url(cuda_version)
    logger.info(f"Selected PyTorch index URL: {pytorch_url}")
    
    execute_pytorch_installation(pytorch_url)
    
    logger.info("PyTorch installation process finished.")

if __name__ == "__main__":
    # A little flair
    print("==============================================")
    print(" PyTorch Installation Helper ")
    print("==============================================")
    main()