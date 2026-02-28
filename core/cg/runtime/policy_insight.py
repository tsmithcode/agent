from __future__ import annotations

import re


def _extract(pattern: str, text: str) -> str:
    m = re.search(pattern, text or "")
    return str(m.group(1)).strip() if m else ""


def policy_key_edit_hint(rule: str, message: str) -> str:
    if rule == "command_allowlist":
        cmd = _extract(r"Command not in allowlist:\s*([^\s]+)", message)
        return f"Add '{cmd or '<command>'}' to command_allowlist in config/policy.json."
    if rule == "command_denylist":
        cmd = _extract(r"Command is explicitly denied by policy:\s*([^\s]+)", message)
        return f"Remove '{cmd or '<command>'}' from command_denylist in config/policy.json."
    if rule == "network_controls.allow_domains":
        host = _extract(r"Domain not allowed by policy:\s*([^\s]+)", message)
        return f"Add '{host or '<domain>'}' to network_controls.allow_domains."
    if rule == "network_controls.allow_outbound_http":
        return "Set network_controls.allow_outbound_http=true."
    if rule == "allowed_write_roots":
        return "Add target path to allowed_write_roots or write inside workspace."
    if rule == "allowed_read_roots":
        return "Run command from a path listed in allowed_read_roots."
    if rule == "denied_paths":
        return "Move command target outside denied_paths."
    if rule.startswith("execution_limits."):
        return f"Increase {rule} in config/policy.json."
    return f"Review and update '{rule}' in config/policy.json."


def policy_violation_insight(*, rule: str, message: str, attempted_action: str) -> dict[str, str]:
    hint = policy_key_edit_hint(rule, message)
    body = (
        f"Attempted action: {attempted_action}\n"
        f"Blocked rule: {rule}\n"
        f"Why blocked: {message}\n"
        f"Policy edit: {hint}\n"
        "After updating policy, retry the same command."
    )
    return {
        "help_line": f"Blocked by {rule}. {hint}",
        "example_line": "cg policy show",
        "body": body,
    }
