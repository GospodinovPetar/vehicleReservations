from typing import Optional

from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string


def render_pair(base_name: str, context: dict) -> tuple[str, Optional[str]]:
    txt_path = f"emails/{base_name}/{base_name}.txt"
    html_path = f"emails/{base_name}/{base_name}.html"
    text_body = render_to_string(txt_path, context)
    try:
        html_body = render_to_string(html_path, context)
    except TemplateDoesNotExist:
        html_body = None
    return text_body, html_body