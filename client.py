import asyncio, json, os
import websockets

SERVER_URL = os.getenv("MCP_SERVER_URL", "ws://127.0.0.1:8765")

async def main():
    async with websockets.connect(SERVER_URL, max_size=2**23) as ws:
        # 1) initialize
        await ws.send(json.dumps({
            "type": "initialize",
            "client": "sample-client",
            "version": "0.1"
        }))
        ready = json.loads(await ws.recv())
        assert ready.get("type") == "ready", f"Unexpected: {ready}"
        print(f"Connected to {ready['server']} with caps {ready['capabilities']}")

        # 2) send an example component prompt
        req = {
            "type": "request",
            "id": "1",
            "method": "llm.generate",
            "params": {
                "prompt": (
                    "You are an electronics expert. "
                    "Compare MLX90393 and HMC5883L Hall/compass sensors for "
                    "resolution, interface, supply voltage, and typical use cases. "
                    "Give a concise bullet list."
                ),
                "system": "Be concise. table format to state the parameters",
                "model": "gpt-4o-mini",
                "temperature": 0.2,
                "format": "markdown"
            }
        }
        await ws.send(json.dumps(req))

        # 3) receive result
        resp = json.loads(await ws.recv())
        if resp.get("type") == "result" and resp.get("ok"):
            data = resp["data"]
            print("\n=== LLM RESPONSE ===\n")
            print(data["text"])
            print("\nUsage:", data.get("usage", {}))
        else:
            print("Error:", resp)

if __name__ == "__main__":
    asyncio.run(main())
