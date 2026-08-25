import sys
import argparse
import urllib.request
import json
import uvicorn

from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.qwen import QwenReasoner
from atlas_core.reasoning.ornith import OrnithReasoner
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.network.server import app

def verify_ollama_model(host: str, model_name: str) -> None:
    """
    Verifies that the Ollama server is running and the requested model is loaded.
    Raises RuntimeError if verification fails.
    """
    api_url = f"{host.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Ollama server returned status code {response.status}")
            
            data = json.loads(response.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            
            # Check if model is pulled
            if model_name in models:
                return
            
            # Fallback check for tagless models (e.g. qwen3:8b vs qwen3:latest)
            short_name = model_name.split(":")[0]
            for m in models:
                if m == model_name or m.split(":")[0] == short_name:
                    return
            
            raise RuntimeError(
                f"Model '{model_name}' is not pulled in Ollama. "
                f"Please run 'ollama pull {model_name}' first."
            )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot connect to Ollama server at '{host}'. "
            "Please ensure Ollama is running."
        ) from e
    except Exception as e:
        raise RuntimeError(f"Ollama verification failed: {str(e)}") from e

def main():
    parser = argparse.ArgumentParser(description="ATLAS OS Network API Server")
    parser.add_argument(
        "--host", 
        type=str, 
        default="0.0.0.0", 
        help="Host address to bind the server to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=9000, 
        help="Port to run the server on (default: 9000)"
    )
    parser.add_argument(
        "--demo", 
        action="store_true", 
        help="Enable Demo Mode with FakeReasoner (bypasses Ollama checks)"
    )
    parser.add_argument(
        "--reasoner", 
        choices=["qwen", "ornith"], 
        default="qwen", 
        help="The production reasoner type to load (default: qwen)"
    )
    parser.add_argument(
        "--model-name", 
        type=str, 
        default=None, 
        help="Custom model name for the reasoner"
    )
    parser.add_argument(
        "--ollama-host", 
        type=str, 
        default="http://localhost:11434", 
        help="Ollama API host (default: http://localhost:11434)"
    )
    
    args = parser.parse_args()

    print("==================================================")
    print("ATLAS OS v1.5 Network Integration Server")
    print("==================================================")

    # 1. Initialize Reasoner based on mode
    if args.demo:
        print("[WARNING] RUNNING IN DEMO MODE!")
        print("Using FakeReasoner (no external LLM calls).")
        print("Bypassing production Ollama connection checks.")
        print("--------------------------------------------------")
        reasoner = FakeReasoner()
    else:
        # Resolve model name
        if args.model_name:
            model = args.model_name
        else:
            model = "qwen3:8b" if args.reasoner == "qwen" else "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
        
        print(f"Booting in PRODUCTION MODE...")
        print(f"Selected Reasoner: {args.reasoner.upper()}")
        print(f"Selected Model:    {model}")
        print(f"Ollama Host:       {args.ollama_host}")
        print("Verifying connection to Ollama and model presence...")
        
        # Verify Ollama is running and has the model
        try:
            verify_ollama_model(args.ollama_host, model)
            print("Ollama connection verified and model is present.")
        except Exception as e:
            print(f"\n[FATAL STARTUP ERROR] {str(e)}", file=sys.stderr)
            print("Please start Ollama or boot with '--demo' for testing.", file=sys.stderr)
            sys.exit(1)

        # Load the real reasoner
        if args.reasoner == "qwen":
            reasoner = QwenReasoner(model_name=model, host=args.ollama_host)
        else:
            reasoner = OrnithReasoner(model_name=model, host=args.ollama_host)

    # 2. Configure Runtime
    config = ATLASConfiguration()
    # Let runtime use SQLiteMemoryStore with temp database or default
    runtime = ATLASRuntime(primary_reasoner=reasoner, configuration=config)
    
    # 3. Inject Runtime into FastAPI app
    app.state.runtime = runtime
    
    print(f"Starting server on {args.host}:{args.port}...")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
