import os
import gc
from sentence_transformers import SentenceTransformer
import torch

from config import SENTENCE_TRANSFORMER_MODEL

class ModelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.model = None
            self.device = None
            self.model_path = None
            self.initialized = True

    def _resolve_device(self, device: str) -> str:
        if device.startswith("cuda") and not torch.cuda.is_available():
            return "cpu"
        return device

    def load_model(self, model_path: str = None, device: str = "cuda:0"):
        if model_path is None:
            model_path = os.environ.get("SENTENCE_TRANSFORMER_MODEL", SENTENCE_TRANSFORMER_MODEL)

        resolved_device = self._resolve_device(device)

        if self.model is None or self.device != resolved_device or self.model_path != model_path:
            if self.model is not None:
                self.release_model()

            if resolved_device != device:
                print(f"Requested device {device} is unavailable, falling back to {resolved_device}")
            print(f"Loading model from {model_path} to {resolved_device}")

            self.model = SentenceTransformer(model_path, device=resolved_device)
            self.device = resolved_device
            self.model_path = model_path
            print(f"Model loaded successfully on {resolved_device}")

            if resolved_device.startswith("cuda"):
                gpu_id = int(resolved_device.split(":")[-1])
                memory_allocated = torch.cuda.memory_allocated(gpu_id) / 1024**3
                memory_reserved = torch.cuda.memory_reserved(gpu_id) / 1024**3
                print(f"GPU {gpu_id} Memory - Allocated: {memory_allocated:.2f}GB, Reserved: {memory_reserved:.2f}GB")
        return self.model
    
    def get_model(self):
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self.model
    
    def encode(self, text: str):
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)

    def release_model(self):
        if self.model is None:
            return

        released_device = self.device
        print(f"Releasing embedding model from {released_device}")
        del self.model
        self.model = None
        self.device = None
        self.model_path = None
        gc.collect()

        if released_device and released_device.startswith("cuda"):
            torch.cuda.empty_cache()
    
    def get_device(self):
        return self.device
    
    def get_memory_usage(self):
        if self.device and self.device.startswith("cuda"):
            gpu_id = int(self.device.split(":")[-1])
            memory_allocated = torch.cuda.memory_allocated(gpu_id) / 1024**3
            memory_reserved = torch.cuda.memory_reserved(gpu_id) / 1024**3
            return {
                "allocated": memory_allocated,
                "reserved": memory_reserved,
                "device": self.device
            }
        return None

model_manager = ModelManager()
