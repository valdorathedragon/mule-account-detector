"""RBI / FIU-IND Suspicious Activity Report synthesis via Gemini with deterministic fallback."""

import json
import os
import re

MODEL_NAME = "gemini-3.8-flash"
MAX_PROMPT_COUNTERPARTIES = 15

SYSTEM_INSTRUCTION = (
    "You are a senior AML Compliance Officer at an Indian scheduled commercial bank, "
    "reporting to the Financial Intelligence Unit - India (FIU-IND) under the Prevention of "
    "Money Laundering Act, 2002 and RBI KYC Master Directions. Write factual, regulator-ready "
    "Suspicious Activity Reports. Never invent figures not present in the evidence."
)


def format_inr(value: float) -> str:
    """Format a number using Indian digit grouping, e.g. 1234567.8 -> INR 12,34,567.80."""
    sign = "-" if value < 0 else ""
    int_part, dec_part = f"{abs(value):.2f}".split(".")
    if len(int_part) > 3:
        head, tail = int_part[:-3], int_part[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        int_part = ",".join(groups + [tail])
    return f"{sign}INR {int_part}.{dec_part}"


def _linked_high_risk_count(account_id: str, risk_tier: str, graph_stats: dict) -> int:
    """Count connected high-risk neighbors, excluding the focal subject account."""
    if "high_risk_nodes" in graph_stats and graph_stats["high_risk_nodes"] is not None:
        return sum(1 for node in graph_stats["high_risk_nodes"] if str(node) != str(account_id))
    raw_count = int(graph_stats.get("high_risk_node_count", 0))
    if risk_tier.upper() == "HIGH" and raw_count > 0:
        return raw_count - 1
    return max(raw_count, 0)


def _tier_guidance(risk_tier: str) -> tuple[str, str]:
    """Return (typology_conclusion, recommended_action) calibrated to risk_tier."""
    tier = risk_tier.upper()
    if tier == "HIGH":
        return (
            "The pattern is consistent with money mule layering indicators under the PMLA, 2002.",
            "It is recommended that the account undergo expedited compliance review, Enhanced Due "
            "Diligence per RBI KYC Master Directions, and FIU-IND Suspicious Transaction Report "
            "(STR) evaluation/filing, with any debit freeze or account restriction subject to "
            "independent verification.",
        )
    if tier == "MEDIUM":
        return (
            "The account exhibits moderate behavioural anomalies that require closer scrutiny "
            "before confirming illicit mule layering.",
            "It is recommended that the account be placed under step-up transaction monitoring "
            "with periodic compliance review; no debit freeze or FIU-IND STR filing is warranted "
            "at this stage without further corroboration.",
        )
    return (
        "The model assigned a LOW risk tier and the available evidence does not establish money "
        "mule layering.",
        "No debit freeze, Enhanced Due Diligence escalation, or FIU-IND STR filing is "
        "recommended; retain standard automated monitoring.",
    )


def _contains_policy_action(text: str) -> bool:
    """Reject LLM text that introduces policy actions, restrictions, or recommendations."""
    return bool(
        re.search(
            r"\b(freeze|restrict(?:ion|ed|ing)?|block(?:ed|ing)?|suspend(?:ed|ing)?|"
            r"hold|close|monitor(?:ing)?|watch|review|escalat(?:e|ion)|report|fil(?:e|ing)|"
            r"due\s+diligence|edd|str\b|fiu|recommend(?:ed|s|ation)?|advise|suggest|"
            r"should|must|action|remediat(?:e|ion))\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _figures_match_evidence(text: str, analysis_payload: dict, graph_stats: dict, linked_count: int) -> bool:
    """Ensure key figures appear accurately and no ungrounded numbers were invented."""
    risk_score = float(analysis_payload.get("risk_score", 0.0))
    inflow_str = format_inr(float(analysis_payload.get("total_inflow", 0.0)))
    outflow_str = format_inr(float(analysis_payload.get("total_outflow", 0.0)))
    ptr = float(analysis_payload.get("pass_through_ratio", 0.0))

    if inflow_str not in text or outflow_str not in text:
        return False

    allowed_nums: set[float] = {
        round(risk_score, 2),
        100.0,
        24.0,
        2.0,
        2002.0,
        round(float(analysis_payload.get("total_inflow", 0.0)), 2),
        round(float(analysis_payload.get("total_outflow", 0.0)), 2),
        round(ptr * 100.0, 2),
        round(ptr, 4),
        float(graph_stats.get("in_degree", 0)),
        float(graph_stats.get("out_degree", 0)),
        abs(round(float(graph_stats.get("degree_asymmetry", 0.0)), 4)),
        float(linked_count),
    }
    for driver in analysis_payload.get("top_drivers", []) or []:
        for tok in re.findall(r"\d[\d,]*\.?\d*", str(driver)):
            allowed_nums.add(round(float(tok.replace(",", "")), 4))

    for raw_tok in re.findall(r"\d[\d,]*\.?\d*", text):
        cleaned = raw_tok.replace(",", "")
        try:
            val = float(cleaned)
        except ValueError:
            continue
        if not any(abs(val - ref) <= 0.05 for ref in allowed_nums):
            return False
    return True


def _build_prompt(analysis_payload: dict, graph_stats: dict) -> str:
    """Compose an evidence-only SAR narrative prompt; actions are appended by policy."""
    payload = dict(analysis_payload)
    payload["counterparties"] = payload.get("counterparties", [])[:MAX_PROMPT_COUNTERPARTIES]
    account = str(payload.get("account_id", "UNKNOWN"))
    tier = str(payload.get("risk_tier", "LOW")).upper()
    linked_count = _linked_high_risk_count(account, tier, graph_stats)

    stats = {
        k: v
        for k, v in graph_stats.items()
        if k not in ("output_path", "high_risk_nodes", "high_risk_node_count")
    }
    stats["linked_high_risk_neighbors"] = linked_count

    typology_rule, _ = _tier_guidance(tier)
    inflow_str = format_inr(float(payload.get("total_inflow", 0.0)))
    outflow_str = format_inr(float(payload.get("total_outflow", 0.0)))
    return (
        "Draft a two-paragraph factual evidence narrative in plain prose (no headings, bullets, "
        "or markdown).\n"
        f"Paragraph 1: Subject account, risk score and tier, total inflow ({inflow_str}) and "
        f"total outflow ({outflow_str}) using those exact INR strings, the Pass-Through Ratio, "
        "and key behavioural observations grounded strictly in the supplied drivers.\n"
        "Paragraph 2: Network topology evidence (in-degree, out-degree, degree asymmetry, fan-in / "
        "fan-out pattern, and linked_high_risk_neighbors excluding the subject), followed by this "
        f"tier-calibrated assessment: {typology_rule}\n"
        "STRICT RULE: Provide factual observations and the typology assessment only. Do NOT "
        "mention any recommended action, debit freeze, restriction, monitoring, due diligence, "
        "or STR/FIU-IND filing—application policy appends the approved action separately.\n\n"
        f"ACCOUNT ANALYSIS:\n{json.dumps(payload, indent=2)}\n\n"
        f"GRAPH TOPOLOGY:\n{json.dumps(stats, indent=2)}"
    )


def _fallback_sar(analysis_payload: dict, graph_stats: dict) -> str:
    """Deterministic tier-calibrated template SAR used when the LLM is unavailable."""
    account = str(analysis_payload.get("account_id", "UNKNOWN"))
    tier = str(analysis_payload.get("risk_tier", "LOW")).upper()
    drivers = analysis_payload.get("top_drivers", []) or ["no dominant driver identified"]
    in_deg = graph_stats.get("in_degree", 0)
    out_deg = graph_stats.get("out_degree", 0)
    asymmetry = float(graph_stats.get("degree_asymmetry", 0.0))
    topology = graph_stats.get("topology", "UNCLASSIFIED")
    linked = _linked_high_risk_count(account, tier, graph_stats)
    ptr = float(analysis_payload.get("pass_through_ratio", 0.0))

    driver_label = (
        "Principal red flags"
        if tier == "HIGH"
        else ("Observed risk indicators" if tier == "MEDIUM" else "Observed activity notes")
    )
    typology_sentence, action_sentence = _tier_guidance(tier)

    paragraph_1 = (
        f"Subject UPI account {account} has been assigned a Risk Score of "
        f"{float(analysis_payload.get('risk_score', 0.0)):.2f}/100 ({tier} tier) by the "
        f"IsolationForest anomaly engine. During the 24-hour review window the account received "
        f"{format_inr(float(analysis_payload.get('total_inflow', 0.0)))} and remitted "
        f"{format_inr(float(analysis_payload.get('total_outflow', 0.0)))}, yielding a Pass-Through "
        f"Ratio of {ptr:.2%}. {driver_label}: {'; '.join(drivers)}."
    )
    paragraph_2 = (
        f"Transaction network analysis places the account in a {topology} position with an "
        f"in-degree of {in_deg}, out-degree of {out_deg} and degree asymmetry of {asymmetry:+.4f}, "
        f"connected to {linked} high-risk neighbor(s) within its 2-hop neighbourhood. "
        f"{typology_sentence} {action_sentence}"
    )
    return f"{paragraph_1}\n\n{paragraph_2}"


def _is_complete_two_paragraph_sar(response: object, text: str, types_mod: object) -> bool:
    """Confirm candidate stopped normally and returned two complete prose paragraphs."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return False

    finish_reason = getattr(candidates[0], "finish_reason", None)
    stop_enum = getattr(getattr(types_mod, "FinishReason", None), "STOP", None)
    is_stop = (stop_enum is not None and finish_reason == stop_enum) or (
        getattr(finish_reason, "name", "").upper() == "STOP"
        or str(finish_reason).upper() in {"STOP", "FINISHREASON.STOP"}
    )
    if not is_stop:
        return False

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paragraphs) != 2:
        return False

    for para in paragraphs:
        if para.startswith(("#", "-", "*")) or para[-1] not in ".!?":
            return False
    return True


def generate_rbi_sar(analysis_payload: dict, graph_stats: dict) -> str:
    """Generate a 2-paragraph SAR with Gemini; fall back to a deterministic template on any failure."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _fallback_sar(analysis_payload, graph_stats)

    try:
        from google import genai
        from google.genai import types

        config_kwargs = {
            "system_instruction": SYSTEM_INSTRUCTION,
            "temperature": 0.2,
            "max_output_tokens": 2048,
        }
        if hasattr(types, "ThinkingConfig"):
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")
            except Exception:
                pass

        with genai.Client(api_key=api_key) as client:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=_build_prompt(analysis_payload, graph_stats),
                config=types.GenerateContentConfig(**config_kwargs),
            )
        text = (response.text or "").strip()
        tier = str(analysis_payload.get("risk_tier", "LOW")).upper()
        account = str(analysis_payload.get("account_id", "UNKNOWN"))
        linked_count = _linked_high_risk_count(account, tier, graph_stats)
        if (
            text
            and _is_complete_two_paragraph_sar(response, text, types)
            and not _contains_policy_action(text)
            and _figures_match_evidence(text, analysis_payload, graph_stats, linked_count)
        ):
            _, action_sentence = _tier_guidance(tier)
            return f"{text} {action_sentence}"
        return _fallback_sar(analysis_payload, graph_stats)
    except Exception:  # offline, rate-limited, invalid key or SDK error
        return _fallback_sar(analysis_payload, graph_stats)
