"""
JARVIS — skills/image_generator.py
Generate images using Hugging Face Inference API (Stable Diffusion) or OpenAI DALL-E API.
"""

import os
import sys
import time
import requests
import shutil
from pathlib import Path

# Add project root to sys.path to allow running this script directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from utils.logger import log


class ImageGeneratorSkill:
    """Generates images from text prompts using Hugging Face or OpenAI APIs."""

    def __init__(self):
        # Create dedicated project generation directory
        self.project_save_dir = Path(__file__).parent.parent / "data" / "generated"
        self.project_save_dir.mkdir(parents=True, exist_ok=True)

        # Detect Windows Desktop path (including OneDrive syncing)
        self.desktop_dir = None
        try:
            standard_desktop = Path(os.path.expanduser("~")) / "Desktop"
            onedrive_desktop = Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"
            if standard_desktop.exists():
                self.desktop_dir = standard_desktop
            elif onedrive_desktop.exists():
                self.desktop_dir = onedrive_desktop
        except Exception as e:
            log.warning(f"Could not determine Desktop directory: {e}")

    def generate_image(self, prompt: str) -> str:
        """
        Generate an image from the prompt, save it locally & on Desktop, and open it.
        
        Args:
            prompt: Text describing the image to generate.

        Returns:
            A spoken feedback message detailing the success or failure.
        """
        prompt = prompt.strip()
        if not prompt:
            return "Please provide a description of the image you want me to generate, sir."

        # ── Determine Provider ─────────────────────────────────────────
        hf_token = config.HF_TOKEN or config.HUGGINGFACE_API_KEY
        openai_key = config.OPENAI_API_KEY

        if not hf_token and not openai_key:
            return (
                "I cannot generate images without API credentials, sir. "
                "Please configure HF_TOKEN or OPENAI_API_KEY in your .env file."
            )

        # ── Check internet connectivity first ──────────────────
        import socket
        def _is_online() -> bool:
            try:
                socket.setdefaulttimeout(3)
                socket.getaddrinfo("8.8.8.8", 80)
                return True
            except Exception:
                return False

        if not _is_online():
            return "I can't generate images right now, sir. No internet connection detected. Try again when you're back online."

        # Use OpenAI if OpenAI is configured and HF is not, or if "dall-e" or "dalle" is in the prompt
        use_openai = False
        if openai_key and (not hf_token or "dalle" in prompt.lower() or "dall-e" in prompt.lower()):
            use_openai = True
            # Clean up the prompt to remove "dalle" instruction words if present
            prompt = prompt.replace("dalle", "").replace("dall-e", "").strip()

        # Sanitize filename from prompt
        safe_name = "".join(c if c.isalnum() or c in (" ", "_", "-") else "" for c in prompt)
        safe_name = safe_name.replace(" ", "_")[:50]  # Limit length
        filename = f"jarvis_{int(time.time())}_{safe_name}.png"

        project_filepath = self.project_save_dir / filename

        log.info(f"Generating image via {'OpenAI DALL-E' if use_openai else 'Hugging Face'} for prompt: '{prompt}'...")

        try:
            if use_openai:
                success = self._generate_via_openai(prompt, project_filepath)
            else:
                success = self._generate_via_huggingface(prompt, project_filepath)

            if not success or not project_filepath.exists():
                return "Image generation failed, sir. Please check the logs."

            # ── Copy to Desktop if available ───────────────────────────
            saved_on_desktop = False
            desktop_filepath = None
            if self.desktop_dir and self.desktop_dir.exists():
                try:
                    desktop_filepath = self.desktop_dir / filename
                    shutil.copy2(project_filepath, desktop_filepath)
                    saved_on_desktop = True
                except Exception as e:
                    log.warning(f"Failed to copy image to Desktop: {e}")

            # ── Auto-Open Image ─────────────────────────────────────────
            try:
                # Open the file using the default OS image viewer
                os.startfile(str(project_filepath))
            except Exception as e:
                log.warning(f"Failed to auto-open generated image: {e}")

            # ── Build Speech Response ──────────────────────────────────
            response_msg = f"I've generated the image for '{prompt}', sir."
            if saved_on_desktop:
                response_msg += " I have saved a copy to your Desktop."
            else:
                response_msg += f" It has been saved in the project's data directory."

            return response_msg

        except Exception as e:
            log.error(f"Error during image generation: {e}")
            return f"An error occurred while generating the image, sir: {str(e)[:100]}"

    def _generate_via_huggingface(self, prompt: str, save_path: Path) -> bool:
        """Call Hugging Face Serverless Inference API to generate image."""
        model = config.IMAGE_GEN_MODEL or "stabilityai/stable-diffusion-xl-base-1.0"
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        
        token = config.HF_TOKEN or config.HUGGINGFACE_API_KEY
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"inputs": prompt}

        # Make the request with retry handling for loading models (503 status code)
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=45)
                
                # Model is loading — sleep and retry
                if response.status_code == 503:
                    try:
                        err_data = response.json()
                        estimated_time = err_data.get("estimated_time", 20.0)
                        log.warning(
                            f"Hugging Face model '{model}' is currently loading. "
                            f"Waiting {estimated_time:.1f}s (Attempt {attempt + 1}/3)..."
                        )
                        time.sleep(min(estimated_time, 15.0))
                        continue
                    except Exception:
                        time.sleep(10.0)
                        continue

                if response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    log.info(f"Image generated and saved to {save_path}")
                    return True
                
                # Unexpected status code
                log.error(f"Hugging Face API returned HTTP {response.status_code}: {response.text}")
                return False

            except requests.RequestException as re:
                err_str = str(re).lower()
                if "nameresolution" in err_str or "getaddrinfo" in err_str:
                    log.error(f"Hugging Face request failed: No internet connection")
                    return False
                log.error(f"Hugging Face request failed: {re}")
                time.sleep(2.0)

        log.error("Failed to generate image via Hugging Face after retries.")
        return False

    def _generate_via_openai(self, prompt: str, save_path: Path) -> bool:
        """Call OpenAI DALL-E API to generate image."""
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.OPENAI_API_KEY}"
        }
        
        # Defaulting to dall-e-3 if possible, else fallback to standard v1 payload
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024"
        }

        try:
            log.info("Attempting image generation with dall-e-3...")
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            
            # If dall-e-3 model fails (e.g. quota limits or unsupported), retry with dall-e-2
            if response.status_code != 200:
                log.warning(f"dall-e-3 request failed (HTTP {response.status_code}): {response.text}")
                log.warning("Retrying with dall-e-2 model...")
                payload["model"] = "dall-e-2"
                response = requests.post(url, json=payload, headers=headers, timeout=45)

            if response.status_code == 200:
                data = response.json()
                img_url = data["data"][0]["url"]
                
                # Download the image from the URL returned
                img_response = requests.get(img_url, timeout=20)
                if img_response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(img_response.content)
                    log.info(f"Image generated via DALL-E and saved to {save_path}")
                    return True
                
            log.error(f"OpenAI API returned HTTP {response.status_code}: {response.text}")
            return False

        except Exception as e:
            log.error(f"OpenAI request failed: {e}")
            return False


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    gen = ImageGeneratorSkill()
    print("Testing image generation...")
    # Will warn if keys are missing
    result = gen.generate_image("A futuristic cybernetic holographic butler standing in a high-tech lab")
    print(result)
