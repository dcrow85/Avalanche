"""Add debug logging to invoke_openai in hypervisor_v44.py"""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "hypervisor_v44.py"

with open(path, "r") as f:
    content = f.read()

old = '''    try:
        record_usage(payload)
        message = payload["choices"][0]["message"]
        content = normalize_structured_output_text(extract_message_text(message))
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed API response: {payload}") from exc'''

new = '''    try:
        record_usage(payload)
        message = payload["choices"][0]["message"]
        raw_text = extract_message_text(message)
        content = normalize_structured_output_text(raw_text)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Debug: log the raw and normalized text to help diagnose format issues
            debug_path = Path("debug_last_response.txt")
            debug_path.write_text(
                f"=== RAW TEXT ({len(raw_text)} chars) ===\\n{raw_text}\\n\\n"
                f"=== NORMALIZED ({len(content)} chars) ===\\n{content}\\n",
                encoding="utf-8",
            )
            raise
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed API response (see debug_last_response.txt): {str(exc)[:500]}") from exc'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("OK: debug logging added")
else:
    print("ERROR: target text not found")
    sys.exit(1)
