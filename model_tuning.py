"""
Model training data generation and tuning configuration for CWOP-Diag.
Generates fine-tuning datasets in Alpaca/ChatML format for automotive diagnostics.
Optimized for Qwen2.5-0.5B/1.5B running on Raspberry Pi.
"""

import json
import os

# ─── Training Data: Expert Automotive Diagnostic Conversations ───
# Each entry is a (system, user, assistant) triple for supervised fine-tuning.

TRAINING_DATA = [
    # ═══ Lean Condition Diagnosis ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0171** [MODERATE]: System Too Lean (Bank 1)\n"
            "  Common causes: Vacuum leak, Faulty MAF sensor, Weak fuel pump\n"
            "**P0174** [MODERATE]: System Too Lean (Bank 2)\n"
            "  Common causes: Vacuum leak, Faulty MAF sensor, Intake manifold gasket leak\n\n"
            "## Live Sensor Data\n"
            "RPM=745 | Coolant Temp=89 C | LTFT B1=+8.2% | LTFT B2=+7.9% | STFT B1=+3.1% | STFT B2=+2.8% | MAF=3.2 g/s\n\n"
            "## Root Cause Correlations\n"
            "1. **P0171 + P0174** (90% confidence)\n"
            "   Root cause: Shared vacuum/intake leak affecting both banks\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "Both banks lean with matching fuel trim patterns — this is a shared air/fuel issue, not bank-specific.\n\n"
            "Root cause: vacuum leak or intake manifold gasket leak. LTFT +8% on both banks confirms the ECU is compensating.\n\n"
            "Diagnostic steps:\n"
            "1. Spray carb cleaner around intake gaskets and vacuum hoses at idle — RPM change = leak found\n"
            "2. Inspect MAF sensor for contamination — unplug and clean with MAF-specific cleaner\n"
            "3. Check fuel pressure at the rail — low pressure affects both banks equally\n"
            "4. If MAF clean and fuel pressure normal, suspect intake manifold gasket\n"
            "5. Smoke test intake system to pinpoint any hidden leaks"
        ),
    },
    # ═══ Misfire Diagnosis ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0300** [HIGH]: Random/Multiple Cylinder Misfire Detected\n"
            "**P0301** [HIGH]: Cylinder 1 Misfire Detected\n"
            "**P0304** [HIGH]: Cylinder 4 Misfire Detected\n\n"
            "## Live Sensor Data\n"
            "RPM=720 | Coolant Temp=91 C | LTFT B1=+2.1% | STFT B1=+5.8% | MAF=3.4 g/s\n\n"
            "## Root Cause Correlations\n"
            "1. **P0300 + P0301 + P0304** (90% confidence)\n"
            "   Root cause: Cylinders 1 & 4 share a coil pack (waste-spark system)\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "Cylinders 1 & 4 misfiring together — classic waste-spark coil failure pattern. These cylinders share a coil pack.\n\n"
            "Root cause: Failed ignition coil pack for cylinders 1/4.\n\n"
            "Diagnostic steps:\n"
            "1. Swap the 1/4 coil pack with the 2/3 coil pack — if misfire moves, coil confirmed bad\n"
            "2. Inspect spark plugs on cylinders 1 & 4 — heavy deposits indicate long-running misfire\n"
            "3. Check plug wires for resistance (if equipped) — should be 5-15k ohms\n"
            "4. If coil swap doesn't move misfire, check fuel injectors on those cylinders\n"
            "5. Compression test cylinders 1 & 4 if ignition components check out"
        ),
    },
    # ═══ Catalyst Efficiency ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0420** [MODERATE]: Catalyst System Efficiency Below Threshold (Bank 1)\n"
            "**P0133** [MODERATE]: O2 Sensor Slow Response (Bank 1 Sensor 1)\n\n"
            "## Live Sensor Data\n"
            "RPM=755 | Coolant Temp=90 C | LTFT B1=+1.2% | O2 B1S1=0.45V\n\n"
            "## Root Cause Correlations\n"
            "1. **P0420 + P0133** (80% confidence)\n"
            "   Root cause: Slow O2 sensor response causing false catalyst code\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "Slow-response O2 sensor B1S1 may be triggering a false catalyst efficiency code. Fuel trims look normal.\n\n"
            "Root cause: Aging upstream O2 sensor — degraded response time mimics failing catalyst on the ECU's efficiency test.\n\n"
            "Diagnostic steps:\n"
            "1. Monitor O2 sensor switching rate at idle — should cycle 6-10 times per 10 seconds\n"
            "2. Replace Bank 1 Sensor 1 O2 sensor (most likely fix at 80% confidence)\n"
            "3. Clear codes and drive 50+ miles to complete readiness monitors\n"
            "4. If P0420 returns after O2 replacement, catalyst is genuinely failing\n"
            "5. Check for exhaust leaks near O2 sensor bung before condemning the cat"
        ),
    },
    # ═══ EVAP System ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0440** [LOW]: Evaporative Emission System Malfunction\n"
            "**P0442** [LOW]: EVAP System Small Leak Detected\n\n"
            "## Live Sensor Data\n"
            "RPM=740 | Coolant Temp=88 C | LTFT B1=+0.5% | Engine Load=18.2%\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "Small EVAP leak — not a drivability concern but will keep check engine light on and fail emissions.\n\n"
            "Most likely cause: gas cap seal degraded or not fully tightened.\n\n"
            "Diagnostic steps:\n"
            "1. Inspect gas cap — check rubber seal for cracks or debris. Tighten until click.\n"
            "2. If cap looks worn, replace it ($10-15 part) — this fixes 60%+ of small EVAP leaks\n"
            "3. Clear codes and drive 2-3 days — if codes return, smoke test the EVAP system\n"
            "4. Common secondary causes: cracked vent hose near canister, faulty purge valve\n"
            "5. All sensor data looks normal — no engine performance concerns"
        ),
    },
    # ═══ Transmission ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0700** [HIGH]: Transmission Control System Malfunction\n"
            "**P0730** [HIGH]: Incorrect Gear Ratio\n\n"
            "## Live Sensor Data\n"
            "RPM=1200 | Speed=0 km/h | Coolant Temp=85 C | Engine Load=22%\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "CRITICAL: Transmission gear ratio error. Vehicle may exhibit harsh shifting, slipping, or failure to engage gears.\n\n"
            "Root cause: Low/contaminated transmission fluid OR internal clutch pack wear.\n\n"
            "Diagnostic steps:\n"
            "1. Check transmission fluid level and condition — dark/burnt fluid = internal damage\n"
            "2. If fluid is low, top up and check for leaks at pan gasket, cooler lines, and seals\n"
            "3. Scan transmission module for additional codes — P0700 is a flag, P0730 is the specific fault\n"
            "4. Test drive monitoring input/output shaft speed sensor readings\n"
            "5. If fluid is clean and level is correct, internal clutch wear likely — transmission shop referral\n\n"
            "⚠️ Avoid extended driving — incorrect gear ratio can cause further transmission damage."
        ),
    },
    # ═══ Overheating ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Active Diagnostic Trouble Codes\n"
            "**P0116** [MODERATE]: Engine Coolant Temperature Range/Performance\n\n"
            "## Live Sensor Data\n"
            "RPM=780 | Coolant Temp=108 C | Engine Load=25% | Intake Temp=42 C\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "⚠️ OVERHEATING RISK: Coolant at 108°C is above normal operating range (85-100°C).\n\n"
            "Root cause: Likely thermostat stuck closed, low coolant, or cooling fan not engaging.\n\n"
            "IMMEDIATE: Do not continue driving if temp rises above 110°C — engine damage risk.\n\n"
            "Diagnostic steps:\n"
            "1. Check coolant level in reservoir and radiator (ENGINE COLD ONLY) — low level = leak or consumption\n"
            "2. Verify cooling fan operation — should engage at ~100°C. Check fan relay and fuse.\n"
            "3. Feel radiator hoses — top hot, bottom cold = stuck thermostat\n"
            "4. Inspect for coolant leaks: water pump weep hole, hoses, radiator, head gasket (white exhaust)\n"
            "5. Replace thermostat ($15-30 part) if stuck — most common fix for this code"
        ),
    },
    # ═══ Clean Vehicle ═══
    {
        "system": "You are an expert automotive diagnostic assistant. Analyze DTCs and sensor data to provide repair recommendations. Be concise (under 150 words).",
        "user": (
            "## Live Sensor Data\n"
            "RPM=740 | Coolant Temp=90 C | LTFT B1=+1.0% | LTFT B2=+0.8% | STFT B1=+0.5% | STFT B2=+0.3% | MAF=3.5 g/s | Engine Load=20% | O2 B1S1=0.45V\n\n"
            "No active trouble codes detected.\n\n"
            "Analyze these DTCs and sensor data."
        ),
        "assistant": (
            "No trouble codes — all sensor readings within normal parameters.\n\n"
            "Vehicle health summary:\n"
            "• RPM: 740 (normal idle range)\n"
            "• Fuel trims: Both banks near zero — fuel system operating correctly\n"
            "• Coolant: 90°C — normal operating temperature\n"
            "• Engine load: 20% at idle — normal\n"
            "• O2 sensor: Active and cycling normally\n\n"
            "Recommendation: Vehicle is running well. Continue regular maintenance per manufacturer schedule."
        ),
    },
    # ═══ Customer-Facing Summaries ═══
    {
        "system": "You are a friendly automotive service advisor explaining vehicle issues to a customer. NO technical jargon. Keep it under 80 words.",
        "user": (
            "Technical findings:\nBoth banks lean with vacuum leak. LTFT B1=+8.2%, LTFT B2=+7.9%.\n\n"
            "Vehicle data:\nP0171: System Too Lean (Bank 1)\nP0174: System Too Lean (Bank 2)\n\n"
            "Explain this to the vehicle owner in simple terms."
        ),
        "assistant": (
            "Your engine isn't getting the right mix of air and fuel — it's running too \"thin\" on the fuel side.\n\n"
            "What this means for you:\n"
            "• You may notice slightly worse fuel economy\n"
            "• The check engine light will stay on until repaired\n"
            "• Safe for short trips, but should be fixed soon\n"
            "• Left alone, it could wear on other engine parts over time\n\n"
            "The likely fix is a small air leak — a routine repair."
        ),
    },
    {
        "system": "You are a friendly automotive service advisor explaining vehicle issues to a customer. NO technical jargon. Keep it under 80 words.",
        "user": (
            "Technical findings:\nCylinders 1 & 4 misfiring — waste-spark coil failure.\n\n"
            "Vehicle data:\nP0300: Random Misfire\nP0301: Cylinder 1 Misfire\nP0304: Cylinder 4 Misfire\n\n"
            "Explain this to the vehicle owner in simple terms."
        ),
        "assistant": (
            "Your engine is running a bit rough because two of its cylinders aren't firing properly.\n\n"
            "What this means for you:\n"
            "• You may feel vibration or a slight shake, especially at idle\n"
            "• Fuel economy is likely reduced\n"
            "• Should be repaired soon to prevent damage to other parts\n"
            "• Usually caused by a worn ignition part that wears out over time\n\n"
            "This is a common repair — replacing the ignition component should fix it right up."
        ),
    },
    {
        "system": "You are a friendly automotive service advisor explaining vehicle issues to a customer. NO technical jargon. Keep it under 80 words.",
        "user": (
            "Technical findings:\nTransmission gear ratio error. Low/contaminated fluid suspected.\n\n"
            "Vehicle data:\nP0700: Transmission Malfunction\nP0730: Incorrect Gear Ratio\n\n"
            "Explain this to the vehicle owner in simple terms."
        ),
        "assistant": (
            "Your vehicle's transmission is having trouble shifting between gears properly.\n\n"
            "What this means for you:\n"
            "• You may feel hard shifts or the car hesitating when accelerating\n"
            "• It's important to get this checked soon to avoid further damage\n"
            "• Often caused by low or old transmission fluid\n"
            "• The repair could be as simple as a fluid change, or it may need further inspection\n\n"
            "We'll check the fluid first — that's the most common and affordable fix."
        ),
    },
]


def generate_alpaca_dataset(output_path="data/training_data_alpaca.json"):
    """Generate training data in Alpaca format for fine-tuning."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    dataset = []

    for entry in TRAINING_DATA:
        dataset.append({
            "instruction": entry["system"],
            "input": entry["user"],
            "output": entry["assistant"],
        })

    with open(output_path, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"[Train] Generated {len(dataset)} training examples -> {output_path}")
    return output_path


def generate_chatml_dataset(output_path="data/training_data_chatml.jsonl"):
    """Generate training data in ChatML/JSONL format for fine-tuning with Unsloth."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w") as f:
        for entry in TRAINING_DATA:
            conversation = {
                "messages": [
                    {"role": "system", "content": entry["system"]},
                    {"role": "user", "content": entry["user"]},
                    {"role": "assistant", "content": entry["assistant"]},
                ]
            }
            f.write(json.dumps(conversation) + "\n")

    print(f"[Train] Generated {len(TRAINING_DATA)} ChatML examples -> {output_path}")
    return output_path


def generate_llama_cpp_prompt_template():
    """Generate the optimal prompt template for llama.cpp inference."""
    return {
        "template": (
            "<|im_start|>system\n{system}<|im_end|>\n"
            "<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n"
        ),
        "stop_tokens": ["<|im_end|>"],
        "parameters": {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "n_predict": 300,
            "min_p": 0.05,
        },
        "notes": (
            "Tuned for Qwen2.5-0.5B/1.5B on Raspberry Pi 5.\n"
            "Lower temperature (0.2) for consistent diagnostic output.\n"
            "repeat_penalty prevents repetitive diagnostic steps.\n"
            "min_p filters low-probability tokens for cleaner output."
        ),
    }


def write_inference_config(output_path="data/inference_config.json"):
    """Write optimized inference configuration for production use."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    config = {
        "model_recommendations": {
            "pi5_4gb": {
                "model": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
                "context_window": 2048,
                "threads": 4,
                "batch_size": 512,
                "notes": "Best for Pi 5 with 4GB RAM. Fast inference, good quality for automotive diagnostics.",
            },
            "pi5_8gb": {
                "model": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "context_window": 2048,
                "threads": 4,
                "batch_size": 512,
                "notes": "Best for Pi 5 with 8GB RAM. Higher quality with acceptable speed.",
            },
            "mac_mini_offload": {
                "model": "qwen2.5-7b-instruct-q4_k_m.gguf",
                "backend": "ollama",
                "notes": "Run on Mac Mini M-series via Ollama for best quality. Pi connects via network.",
            },
        },
        "llama_server_args": {
            "pi5": [
                "--threads", "4",
                "--ctx-size", "2048",
                "--batch-size", "512",
                "--mlock",
                "--no-mmap",
                "--host", "127.0.0.1",
                "--port", "8080",
            ],
        },
        "prompt_engineering": {
            "system_prompt_version": "2.0",
            "tech_prompt_features": [
                "Root cause correlation integration",
                "Health score context",
                "Freeze frame data support",
                "Vehicle-specific context (VIN decoded)",
                "Service history awareness",
            ],
            "customer_prompt_features": [
                "Health score grade explanation",
                "Cost context integration",
                "Safety-first communication",
                "Reassurance patterns",
            ],
        },
        "fine_tuning": {
            "method": "LoRA via Unsloth",
            "base_model": "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit",
            "lora_config": {
                "r": 16,
                "lora_alpha": 32,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
                "lora_dropout": 0.05,
            },
            "training_config": {
                "epochs": 3,
                "learning_rate": 2e-4,
                "batch_size": 2,
                "gradient_accumulation_steps": 4,
                "warmup_ratio": 0.1,
                "max_seq_length": 2048,
            },
            "export": {
                "format": "gguf",
                "quantization": "q4_k_m",
                "output": "cwop-diag-qwen2.5-1.5b-auto-q4_k_m.gguf",
            },
            "instructions": (
                "1. Install Unsloth: pip install unsloth\n"
                "2. Generate training data: python -c 'from model_tuning import *; generate_chatml_dataset()'\n"
                "3. Fine-tune with the ChatML dataset using Unsloth's Qwen2.5 template\n"
                "4. Export to GGUF Q4_K_M format\n"
                "5. Replace the base model in ~/models/ with the fine-tuned GGUF\n"
                "6. Restart llama-server"
            ),
        },
    }

    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"[Train] Wrote inference config -> {output_path}")
    return output_path


if __name__ == "__main__":
    generate_alpaca_dataset()
    generate_chatml_dataset()
    write_inference_config()
    print("\nAll training data and configs generated in data/")
