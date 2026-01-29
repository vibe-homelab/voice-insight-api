"""Base worker class for all workers."""

import argparse
from abc import ABC, abstractmethod

import uvicorn
from fastapi import FastAPI


class BaseWorker(ABC):
    """Base class for STT/TTS workers."""

    def __init__(self, alias: str, model_path: str, port: int):
        self.alias = alias
        self.model_path = model_path
        self.port = port
        self.app = FastAPI(title=f"Voice Worker: {alias}")
        self._setup_routes()

    def _setup_routes(self):
        """Setup common routes."""
        @self.app.get("/health")
        async def health():
            return {"status": "healthy", "alias": self.alias}

    @abstractmethod
    def load_model(self):
        """Load the ML model."""
        pass

    def run(self):
        """Run the worker server."""
        self.load_model()
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)

    @classmethod
    def parse_args(cls):
        """Parse command line arguments."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--alias", required=True)
        parser.add_argument("--model_path", required=True)
        parser.add_argument("--port", type=int, required=True)
        return parser.parse_args()
