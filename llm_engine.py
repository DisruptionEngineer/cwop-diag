"""
LLM inference engine for CWOP-Diag.
Supports three backends:
  1. llama.cpp HTTP server (recommended for Pi — lowest overhead)
  2. Ollama API (easier setup, slightly more overhead)
  3. Demo mode (returns canned responses for testing without any LLM)
"""

import json
import requests
import time

# System prompt for the tech-facing diagnostic assistant
SYSTEM_PROMPT = """You are an expert automotive diagnostic assistant running on a Raspberry Pi.
You analyze OBD-II diagnostic trouble codes (DTCs) and live sensor data to provide repair recommendations.

Rules:
- Be concise. The display is 720x720 pixels — keep responses under 150 words.
- Start with the most likely cause based on the DTC pattern and sensor data.
- Consider how multiple DTCs relate to each other (root cause analysis).
- Suggest diagnostic steps in order from simplest/cheapest to most complex.
- Flag safety-critical issues (brakes, steering, fuel leaks) prominently.
- Use plain language a novice can understand, but include technical terms in parentheses.
- If fuel trims are provided, analyze them for lean/rich patterns.
- Format: Start with a 1-line summary, then numbered diagnostic steps."""

# System prompt for the customer-facing summary
CUSTOMER_PROMPT = """You are a friendly automotive service advisor explaining vehicle issues to a customer.
The customer is NOT a mechanic — use simple, everyday language.

Rules:
- NO technical jargon (no "DTCs", "fuel trims", "MAF", "O2 sensor", "ECU" etc.)
- Explain what the problem MEANS for them: safety, reliability, fuel economy.
- Be honest but reassuring — don't scare them unnecessarily.
- Keep it under 80 words.
- Start with a 1-2 sentence summary of the problem.
- Then a short bullet list (3-4 items) of what it means for the driver.
- End with one reassuring sentence about the repair.
- Use "your vehicle" not "the vehicle"."""


class LLMEngine:
    """Interface to local LLM inference."""

    def __init__(self, backend: str = "llamacpp", base_url: str = None, model: str = None):
        """
        Args:
            backend: "llamacpp", "ollama", or "demo"
            base_url: API endpoint
                - llama.cpp: http://localhost:8080
                - ollama: http://localhost:11434
            model: Model name (for Ollama only, e.g. "qwen2.5:1.5b")
        """
        self.backend = backend
        self.model = model or "qwen2.5:1.5b"

        if base_url:
            self.base_url = base_url.rstrip("/")
        elif backend == "llamacpp":
            self.base_url = "http://localhost:8080"
        elif backend == "ollama":
            self.base_url = "http://localhost:11434"
        else:
            self.base_url = ""

    def diagnose(self, dtc_context: str, question: str = None) -> dict:
        """
        Run a diagnostic analysis (tech-facing).

        Args:
            dtc_context: Formatted string from DTCDatabase.format_for_llm()
            question: Optional user question (otherwise uses default analysis prompt)

        Returns:
            {"response": str, "tokens": int, "duration_ms": int}
        """
        if question:
            user_msg = f"{dtc_context}\n\n## User Question\n{question}"
        else:
            user_msg = (
                f"{dtc_context}\n\n"
                "Analyze these DTCs and sensor data. "
                "What is the most likely root cause? "
                "Provide step-by-step diagnostic recommendations."
            )

        start = time.time()

        if self.backend == "demo":
            result = self._demo_response(dtc_context)
        elif self.backend == "llamacpp":
            result = self._llamacpp_completion(SYSTEM_PROMPT, user_msg)
        elif self.backend == "ollama":
            result = self._ollama_completion(SYSTEM_PROMPT, user_msg)
        else:
            result = {"response": f"Unknown backend: {self.backend}", "tokens": 0}

        elapsed = int((time.time() - start) * 1000)
        result["duration_ms"] = elapsed
        return result

    def customer_summary(self, context: str, tech_diagnosis: str) -> dict:
        """
        Generate a customer-friendly summary of the diagnosis.

        Args:
            context: Assembled CWOP context (DTCs + sensor data)
            tech_diagnosis: The tech-facing diagnosis text

        Returns:
            {"response": str, "tokens": int, "duration_ms": int}
        """
        user_msg = (
            f"Technical findings:\n{tech_diagnosis}\n\n"
            f"Vehicle data:\n{context}\n\n"
            "Explain this to the vehicle owner in simple terms."
        )

        start = time.time()

        if self.backend == "demo":
            result = self._demo_customer_response(context)
        elif self.backend == "llamacpp":
            result = self._llamacpp_completion(CUSTOMER_PROMPT, user_msg, max_tokens=200)
        elif self.backend == "ollama":
            result = self._ollama_completion(CUSTOMER_PROMPT, user_msg, max_tokens=200)
        else:
            result = self._demo_customer_response(context)

        elapsed = int((time.time() - start) * 1000)
        result["duration_ms"] = elapsed
        return result

    def health_check(self) -> bool:
        """Check if the LLM backend is reachable."""
        if self.backend == "demo":
            return True
        try:
            if self.backend == "llamacpp":
                r = requests.get(f"{self.base_url}/health", timeout=3)
                return r.status_code == 200
            elif self.backend == "ollama":
                r = requests.get(f"{self.base_url}/api/tags", timeout=3)
                return r.status_code == 200
        except Exception:
            return False

    def _llamacpp_completion(self, system_prompt: str, user_msg: str, max_tokens: int = 300) -> dict:
        """Call llama.cpp HTTP server (/completion endpoint)."""
        prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        try:
            r = requests.post(
                f"{self.base_url}/completion",
                json={
                    "prompt": prompt,
                    "n_predict": max_tokens,
                    "temperature": 0.3,
                    "stop": ["<|im_end|>"],
                    "stream": False,
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "response": data.get("content", "").strip(),
                "tokens": data.get("tokens_predicted", 0),
            }
        except requests.exceptions.ConnectionError:
            return {"response": "LLM server not running. Start llama-server first.", "tokens": 0}
        except Exception as e:
            return {"response": f"LLM error: {e}", "tokens": 0}

    def _ollama_completion(self, system_prompt: str, user_msg: str, max_tokens: int = 300) -> dict:
        """Call Ollama API (/api/chat endpoint)."""
        try:
            r = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            msg = data.get("message", {})
            return {
                "response": msg.get("content", "").strip(),
                "tokens": data.get("eval_count", 0),
            }
        except requests.exceptions.ConnectionError:
            return {"response": "Ollama not running. Start with: ollama serve", "tokens": 0}
        except Exception as e:
            return {"response": f"Ollama error: {e}", "tokens": 0}

    # ─── Demo Responses ────────────────────────────────────────────

    def _demo_response(self, dtc_context: str) -> dict:
        """Return a realistic canned response for demo/testing."""
        if "P0171" in dtc_context and "P0174" in dtc_context:
            response = (
                "Both banks running lean — this points to a shared air/fuel issue, "
                "not a bank-specific problem.\n\n"
                "Most likely cause: vacuum leak or intake manifold gasket leak.\n\n"
                "Diagnostic steps:\n"
                "1. Check for vacuum leaks — spray carb cleaner around intake gaskets "
                "and vacuum hoses while idling. RPM change = leak found.\n"
                "2. Inspect the MAF sensor — unplug it and check for contamination. "
                "Clean with MAF-specific cleaner (not carb cleaner).\n"
                "3. Check fuel pressure — low pressure affects both banks equally.\n"
                "4. Look at long-term fuel trims — values above +10% confirm the "
                "ECU is compensating for a lean condition.\n"
                "5. If LTFT is high and MAF is clean, suspect intake manifold gasket."
            )
        elif "P0300" in dtc_context:
            response = (
                "Random misfire across multiple cylinders — usually not a single "
                "ignition component.\n\n"
                "Most likely cause: fuel delivery issue or vacuum leak.\n\n"
                "Diagnostic steps:\n"
                "1. Check spark plugs — worn plugs cause random misfires.\n"
                "2. Check fuel pressure at the rail.\n"
                "3. Look for vacuum leaks.\n"
                "4. If misfires are worse at idle, suspect vacuum leak.\n"
                "5. If misfires are worse under load, suspect fuel delivery."
            )
        else:
            response = (
                "DTC analysis complete. Check the specific trouble codes above "
                "and address in order of severity (HIGH first).\n\n"
                "General diagnostic steps:\n"
                "1. Address any HIGH severity codes first — these affect drivability.\n"
                "2. Check for related codes that share a root cause.\n"
                "3. Inspect wiring and connectors for the affected circuits.\n"
                "4. Clear codes and drive to see which return."
            )

        return {"response": response, "tokens": len(response.split())}

    def _demo_customer_response(self, context: str) -> dict:
        """Return a customer-friendly canned response for demo/testing."""
        if "P0171" in context and "P0174" in context:
            response = (
                "Your vehicle's engine isn't getting the right mix of air and fuel. "
                "This is a common issue that's straightforward to fix.\n\n"
                "What this means for you:\n"
                "\u2022 You may notice slightly reduced fuel economy\n"
                "\u2022 The check engine light will stay on until repaired\n"
                "\u2022 Safe to drive short distances, but should be fixed soon\n"
                "\u2022 Left unrepaired, it could stress other engine parts\n\n"
                "The most likely fix involves checking for a small air leak \u2014 "
                "a routine repair that most shops handle regularly."
            )
        elif "P0300" in context:
            response = (
                "Your engine is occasionally running rough, which means "
                "it's not firing on all cylinders consistently.\n\n"
                "What this means for you:\n"
                "\u2022 You may feel vibration or hesitation while driving\n"
                "\u2022 Fuel economy is likely reduced\n"
                "\u2022 Should be addressed soon to prevent further wear\n"
                "\u2022 Usually caused by parts that wear out over time\n\n"
                "This is typically a spark plug or ignition part replacement \u2014 "
                "a common maintenance repair."
            )
        else:
            response = (
                "Your vehicle's onboard computer has flagged some items "
                "that need attention.\n\n"
                "What this means for you:\n"
                "\u2022 Your check engine light is on for a specific reason\n"
                "\u2022 The issues range from minor to moderate in severity\n"
                "\u2022 Getting these addressed keeps your vehicle reliable\n"
                "\u2022 Our technician has reviewed the data thoroughly\n\n"
                "We've prepared a detailed repair plan for your vehicle."
            )

        return {"response": response, "tokens": len(response.split())}
