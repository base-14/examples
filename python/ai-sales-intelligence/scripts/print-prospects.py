#!/usr/bin/env python3
"""Pretty-print prospect outcomes from the sales intelligence API.

Usage: curl -s http://localhost:8000/campaigns/<id>/prospects | python3 scripts/print-prospects.py
"""

import json
import sys
import textwrap


CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[90m"
RESET = "\033[0m"


def print_prospects(prospects: list[dict]) -> None:  # noqa: PLR0912, PLR0915
    if not prospects:
        print("  (no prospects)")
        return

    for i, p in enumerate(prospects):
        enrichment = p.get("enrichment") or {}
        industry = enrichment.get("industry", "-")
        company_size = enrichment.get("company_size", "-")
        tech_stack = enrichment.get("tech_stack", [])
        pain_points = enrichment.get("pain_points", [])
        recent_news = enrichment.get("recent_news")
        confidence = enrichment.get("confidence")
        score = p.get("icp_score")
        reasoning = p.get("score_reasoning") or ""
        qscore = p.get("quality_score")
        qpassed = p.get("quality_passed")
        subject = p.get("email_subject") or "-"
        body = p.get("email_body") or ""

        cid = p.get("connection_id", "?")[:8]
        if qpassed:
            quality_label = f"{GREEN}\u2713 passed{RESET}"
        elif qpassed is False:
            quality_label = f"{YELLOW}\u2717 failed{RESET}"
        else:
            quality_label = f"{YELLOW}(not evaluated){RESET}"

        print("")
        print(f"  {CYAN}\u2501\u2501\u2501 Prospect {i+1}: {cid}\u2026 \u2501\u2501\u2501{RESET}")
        print("")

        # Enrich
        print(f"  {CYAN}Enrich{RESET}")
        print(f"    Industry:    {industry}")
        print(f"    Size:        {company_size}")
        print(f"    Confidence:  {confidence}")
        if tech_stack:
            ts = ", ".join(tech_stack[:6])
            suffix = "\u2026" if len(tech_stack) > 6 else ""
            print(f"    Tech stack:  {ts}{suffix}")
        if pain_points:
            for pp in pain_points[:3]:
                print(f"    Pain point:  {pp}")
            if len(pain_points) > 3:
                print(f"    {DIM}\u2026 and {len(pain_points) - 3} more{RESET}")
        if recent_news:
            wrapped = textwrap.shorten(recent_news, width=80, placeholder="\u2026")
            print(f"    News:        {wrapped}")

        # Score
        print("")
        print(f"  {CYAN}Score{RESET} \u2014 {score}/100")
        if reasoning:
            for line in textwrap.wrap(reasoning, width=76):
                print(f"    {DIM}{line}{RESET}")

        # Draft
        print("")
        print(f"  {CYAN}Draft{RESET}")
        print(f"    Subject: {subject}")
        print("    \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        if body:
            for line in body.strip().split("\n"):
                print(f"    {line}")
        print("    \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        # Evaluate
        print("")
        qscore_display = qscore or "\u2014"
        print(f"  {CYAN}Evaluate{RESET} \u2014 {qscore_display}/100 {quality_label}")
        if qscore is None and subject != "-":
            print(f"    {YELLOW}NOTE{RESET} evaluate ran but quality_score not saved")
        print("")


if __name__ == "__main__":
    prospects = json.load(sys.stdin)
    print_prospects(prospects)
