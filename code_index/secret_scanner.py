import re
import math
import string


SECRET_PATTERNS = [
    (re.compile(r'AKIA[0-9A-Z]{16}'), "aws_access_key_id"),
    (re.compile(r'(?:AWS_SECRET_ACCESS_KEY|aws_secret_access_key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{40})["\']?'), "aws_secret_access_key"),
    (re.compile(r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*'), "jwt_token"),
    (re.compile(r'(?:postgres|postgresql|mysql|mongodb|redis)(?:\+[\w]+)?://[^\s"\'<>]+'), "database_connection_string"),
    (re.compile(r'gh[psrupoa]_[A-Za-z0-9_]{36,}'), "github_token"),
    (re.compile(r'xox[bpars]-[A-Za-z0-9-]+'), "slack_token"),
    (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----'), "private_key"),
    (re.compile(r'(?:api[_-]?key|apikey|secret[_-]?key|auth[_-]?token|access[_-]?token|bearer)\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', re.IGNORECASE), "generic_api_key"),
    (re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\']([^"\']{8,})["\']', re.IGNORECASE), "password"),
    (re.compile(r'sk_live_[A-Za-z0-9]{24,}'), "stripe_secret_key"),
    (re.compile(r'rk_live_[A-Za-z0-9]{24,}'), "stripe_restricted_key"),
    (re.compile(r'pk_live_[A-Za-z0-9]{24,}'), "stripe_publishable_key"),
    (re.compile(r'AZURE_[A-Z_]*\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']', re.IGNORECASE), "azure_credential"),
    (re.compile(r'[a-z0-9]{32}-[a-z0-9]{32}\.apps\.googleusercontent\.com'), "gcp_oauth_client_id"),
    (re.compile(r'AIza[A-Za-z0-9_\-]{35}'), "google_api_key"),
    (re.compile(r'eyJhb[A-Za-z0-9_\-]*\.eyJ[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*'), "gcp_service_account_token"),
    (re.compile(r'sq0idp-[A-Za-z0-9_\-]{22,}'), "square_access_token"),
    (re.compile(r'sq0csp-[A-Za-z0-9_\-]{43,}'), "square_oauth_secret"),
    (re.compile(r'key_[a-z0-9]{32,}'), "sendgrid_api_key"),
    (re.compile(r'SG\.[A-Za-z0-9_\-]{22,}\.[A-Za-z0-9_\-]{43,}'), "sendgrid_full_api_key"),
    (re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'), "generic_uuid"),
    (re.compile(r'(?:token|key|secret|api[_-]?key|apikey|auth[_-]?token|access[_-]?token|bearer|credential|private[_-]?key)\s*[=:]\s*["\']([A-Za-z0-9_\-/+=]{20,})["\']', re.IGNORECASE), "generic_secret_assignment"),
]


def _shannon_entropy(data):
    if not data:
        return 0.0
    freq = {}
    for ch in data:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(data)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


HIGH_ENTROPY_PATTERN = re.compile(r'["\']([A-Za-z0-9+/=._-]{30,})["\']')
UNQUOTED_SECRET_PATTERN = re.compile(r'(?:api[_-]?key|secret|token|password|passwd|pwd|credential|auth)\s*[=:]\s*([A-Za-z0-9_\-/+=]{20,})', re.IGNORECASE)


def _check_entropy(text):
    findings = []
    for match in HIGH_ENTROPY_PATTERN.finditer(text):
        candidate = match.group(1)
        entropy = _shannon_entropy(candidate)
        is_base64 = bool(re.match(r'^[A-Za-z0-9+/]+=*$', candidate))
        is_hex = bool(re.match(r'^[0-9a-fA-F]+$', candidate))
        if (is_base64 and entropy > 4.5) or (is_hex and entropy > 3.0) or entropy > 5.0:
            findings.append((match.start(1), match.end(1), "high_entropy_string", candidate))
    return findings


def _check_unquoted_secrets(text):
    findings = []
    for match in UNQUOTED_SECRET_PATTERN.finditer(text):
        candidate = match.group(1)
        if candidate.lower() in ("true", "false", "none", "null", "undefined"):
            continue
        findings.append((match.start(1), match.end(1), "unquoted_secret", candidate))
    return findings


def scan_and_redact(text):
    findings = []
    redacted = text

    for pattern, secret_type in SECRET_PATTERNS:
        for match in pattern.finditer(redacted):
            group = match.group(1) if match.lastindex else match.group(0)
            if group:
                placeholder = "***REDACTED_SECRET***"
                redacted = redacted[:match.start()] + placeholder + redacted[match.end():]
                findings.append({"type": secret_type, "value": group[:8] + "..."})

    for start, end, stype, value in _check_entropy(redacted):
        placeholder = "***REDACTED_SECRET***"
        redacted = redacted[:start] + placeholder + redacted[end:]
        findings.append({"type": stype, "value": value[:8] + "..."})

    for start, end, stype, value in _check_unquoted_secrets(redacted):
        placeholder = "***REDACTED_SECRET***"
        redacted = redacted[:start] + placeholder + redacted[end:]
        findings.append({"type": stype, "value": value[:8] + "..."})

    return redacted, findings


def redact_chunk(chunk):
    redacted_text, findings = scan_and_redact(chunk["text"])
    new_chunk = dict(chunk)
    new_chunk["text"] = redacted_text
    if findings:
        new_chunk["redacted_secrets"] = findings
    return new_chunk
