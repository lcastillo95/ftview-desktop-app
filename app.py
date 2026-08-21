import html
import io
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog
import xml.etree.ElementTree as ET
import webview


class FlattenedFTViewCompiler:

  def __init__(
      self, xml_bytes: bytes, file_name: str, tag_overrides: dict = None
  ):
    self.file_name = file_name
    self.tree = ET.parse(io.BytesIO(xml_bytes))
    self.root = self.tree.getroot()
    self.tag_overrides = tag_overrides or {}

    settings = self.root.find(".//displaySettings")
    if settings is not None:
      self.width = int(settings.attrib.get("width", 1920))
      self.height = int(settings.attrib.get("height", 1080))
      self.bg_color = settings.attrib.get("backColor", "#EEE7D7")
    else:
      self.width = 1920
      self.height = 1080
      self.bg_color = "#EEE7D7"

  def _get_transform(self, elem) -> str:
    t = elem.find("./transform")
    if t is None:
      return ""
    a = t.attrib.get("scaleWidth", "1")
    b = t.attrib.get("shearHeight", "0")
    c = t.attrib.get("shearWidth", "0")
    d = t.attrib.get("scaleHeight", "1")
    e = t.attrib.get("offsetWidth", "0")
    f = t.attrib.get("offsetHeight", "0")
    return f'transform="matrix({a} {b} {c} {d} {e} {f})"'

  def _extract_local_tags(self, elem) -> list:
    info = []
    name = elem.attrib.get("name", "")
    if name:
      info.append(f"Name: {name}")

    for conn in elem.findall("./connections/connection"):
      expr = conn.attrib.get("expression")
      conn_name = conn.attrib.get("name", "Value")
      if expr:
        info.append(f"Conn ({conn_name}): {expr}")

    for anim in elem.findall("./animations/*"):
      anim_type = anim.tag.replace("animate", "")
      expr = anim.attrib.get("expression")
      rel = anim.attrib.get("releaseAction")
      prs = anim.attrib.get("pressAction")
      if expr:
        info.append(f"Anim ({anim_type}): {expr}")
      if rel:
        info.append(f"Release: {rel}")
      if prs:
        info.append(f"Press: {prs}")

    for act in elem.findall("./action"):
      t = act.attrib.get("tag")
      act_type = act.attrib.get("type", "Action")
      if t:
        info.append(f"Action ({act_type}): {t}")

    for cmd in elem.findall("./command"):
      rel = cmd.attrib.get("releaseAction")
      prs = cmd.attrib.get("pressAction")
      if rel:
        info.append(f"Cmd (Release): {rel}")
      if prs:
        info.append(f"Cmd (Press): {prs}")

    return info

  def _build_tag_attr(self, tag_list: list) -> str:
    if not tag_list:
      return ""
    unique = []
    for item in tag_list:
      if item not in unique:
        unique.append(item)
    escaped = html.escape(" | ".join(unique), quote=True)
    return f' data-tag-info="{escaped}" class="has-tag-info"'

  def _render_primitive(self, elem, accumulated_tags: list) -> str:
    tag = elem.tag
    tf = self._get_transform(elem)
    elem_tags = list(accumulated_tags)
    for lt in self._extract_local_tags(elem):
      if lt not in elem_tags:
        elem_tags.append(lt)

    tag_attr = self._build_tag_attr(elem_tags)

    if tag == "multistateIndicator":
      x = float(elem.attrib.get("left", 0))
      y = float(elem.attrib.get("top", 0))
      w = float(elem.attrib.get("width", 0))
      h = float(elem.attrib.get("height", 0))
      conn = elem.find(".//connection")
      tag_expr = conn.attrib.get("expression") if conn is not None else None
      active_id = str(
          self.tag_overrides.get(
              tag_expr, elem.attrib.get("currentStateId", "0")
          )
      )

      matched_state = None
      for s in elem.findall(".//state"):
        if (
            s.attrib.get("stateId") == active_id
            or s.attrib.get("value") == active_id
        ):
          matched_state = s
          break
      if matched_state is None:
        matched_state = elem.find(".//state")

      bg = (
          matched_state.attrib.get("backColor", "navy")
          if matched_state is not None
          else "navy"
      )
      cap_node = (
          matched_state.find(".//caption") if matched_state is not None else None
      )
      raw_text = (
          cap_node.attrib.get("caption", "") if cap_node is not None else ""
      )
      txt_color = (
          cap_node.attrib.get("color", "white")
          if cap_node is not None
          else "white"
      )
      size = (
          int(cap_node.attrib.get("fontSize", 10))
          if cap_node is not None
          else 10
      )
      bold = (
          "bold"
          if cap_node is not None and cap_node.attrib.get("bold") == "true"
          else "normal"
      )

      clean_text = raw_text.replace("&#xA;", "\n").replace("\r\n", "\n")
      lines = clean_text.split("\n")
      out = [
          f"<g {tf} {tag_attr}>",
          (
              f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"'
              ' stroke="#000000" stroke-width="1"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x},{y} {x+w},{y}"'
              ' stroke="rgba(255,255,255,0.5)" stroke-width="2" fill="none"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x+w},{y+h} {x+w},{y}"'
              ' stroke="rgba(0,0,0,0.5)" stroke-width="2" fill="none"/>'
          ),
      ]
      total_h = len(lines) * (size + 3)
      start_y = y + (h / 2) - (total_h / 2) + (size / 2)
      for i, line in enumerate(lines):
        line_y = start_y + i * (size + 3)
        out.append(
            f'<text x="{x + w/2}" y="{line_y}" font-family="Arial"'
            f' font-size="{size}px" font-weight="{bold}" fill="{txt_color}"'
            f' text-anchor="middle">{html.escape(line)}</text>'
        )
      out.append("</g>")
      return "".join(out)

    elif tag == "rectangle":
      x = float(elem.attrib.get("left", 0))
      y = float(elem.attrib.get("top", 0))
      w = float(elem.attrib.get("width", 0))
      h = float(elem.attrib.get("height", 0))
      is_trans = elem.attrib.get("backStyle") == "transparent"
      fill = "none" if is_trans else elem.attrib.get("backColor", "#FFFFFF")
      stroke = elem.attrib.get("foreColor", "none") if not is_trans else "none"
      lw = elem.attrib.get("lineWidth", "1")
      return (
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"'
          f' stroke="{stroke}" stroke-width="{lw}" {tf} {tag_attr}/>'
      )

    elif tag == "line":
      pts = elem.attrib.get("line", "").strip().split()
      if len(pts) >= 4:
        stroke = (
            elem.attrib.get("backColor")
            or elem.attrib.get("foreColor")
            or "#000000"
        )
        lw = elem.attrib.get("lineWidth", "1")
        return (
            f'<line x1="{pts[0]}" y1="{pts[1]}" x2="{pts[2]}" y2="{pts[3]}"'
            f' stroke="{stroke}" stroke-width="{lw}" stroke-linecap="square"'
            f" {tf} {tag_attr}/>"
        )

    elif tag in ("polygon", "polyline"):
      raw = elem.attrib.get("path", "").strip().split()
      coords = " ".join(
          [f"{raw[i]},{raw[i+1]}" for i in range(0, len(raw) - 1, 2)]
      )
      fill = (
          elem.attrib.get("backColor", "#999999")
          if tag == "polygon"
          else "none"
      )
      stroke = elem.attrib.get("foreColor", "#000000")
      lw = elem.attrib.get("lineWidth", "1")
      tag_name = "polygon" if tag == "polygon" else "polyline"
      return (
          f'<{tag_name} points="{coords}" fill="{fill}" stroke="{stroke}"'
          f' stroke-width="{lw}" {tf} {tag_attr}/>'
      )

    elif tag == "text":
      x = float(elem.attrib.get("left", 0))
      y = float(elem.attrib.get("top", 0))
      w = float(elem.attrib.get("width", 0))
      h = float(elem.attrib.get("height", 0))
      size = int(
          elem.attrib.get("fontSize") or elem.attrib.get("charHeight") or 11
      )
      raw_text = elem.attrib.get("caption", "")
      clean_text = raw_text.replace("&#xA;", "\n").replace("\r\n", "\n")
      lines = clean_text.split("\n")
      color = elem.attrib.get("foreColor", "#000000")
      bold = "bold" if elem.attrib.get("bold") == "true" else "normal"
      anchor = "middle" if w > 0 else "start"
      anchor_x = x + (w / 2 if w > 0 else 0)

      tspans = []
      total_h = len(lines) * (size + 3)
      start_y = (
          (y + h / 2 - total_h / 2 + size / 2) if h > 0 else (y + size / 2)
      )
      for i, line in enumerate(lines):
        line_y = start_y + i * (size + 3)
        tspans.append(
            f'<text x="{anchor_x}" y="{line_y}" font-family="Arial"'
            f' font-size="{size}px" font-weight="{bold}" fill="{color}"'
            f' text-anchor="{anchor}">{html.escape(line)}</text>'
        )
      return f"<g {tf} {tag_attr}>" + "".join(tspans) + "</g>"

    elif tag == "button":
      x = float(elem.attrib.get("left", 0))
      y = float(elem.attrib.get("top", 0))
      w = float(elem.attrib.get("width", 0))
      h = float(elem.attrib.get("height", 0))
      up = elem.find(".//up")
      bg = up.attrib.get("backColor", "#D4D0C8") if up is not None else "#D4D0C8"
      fg = up.attrib.get("foreColor", "#000000") if up is not None else "#000000"
      cap_elem = elem.find(".//caption")
      raw_cap = cap_elem.attrib.get("caption", "") if cap_elem is not None else ""
      clean_cap = raw_cap.replace("&#xA;", "\n").replace("\r\n", "\n")
      size = (
          int(cap_elem.attrib.get("fontSize", 10))
          if cap_elem is not None
          else 10
      )
      lines = clean_cap.split("\n")
      out = [
          f'<g class="hmi-button" {tf} {tag_attr}>',
          f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"/>',
          (
              f'<polyline points="{x},{y+h} {x},{y} {x+w},{y}" stroke="#FFFFFF"'
              ' stroke-width="2" fill="none"/>'
          ),
          (
              f'<polyline points="{x},{y+h} {x+w},{y+h} {x+w},{y}"'
              ' stroke="#404040" stroke-width="2" fill="none"/>'
          ),
      ]
      start_y = y + h / 2 - (len(lines) * (size + 2)) / 2 + size / 2
      for i, line in enumerate(lines):
        out.append(
            f'<text x="{x + w/2}" y="{start_y + i*(size+2)}"'
            f' font-family="Arial" font-size="{size}px" font-weight="bold"'
            f' fill="{fg}" text-anchor="middle">{html.escape(line)}</text>'
        )
      out.append("</g>")
      return "".join(out)

    elif tag in ("numericDisplay", "stringDisplay"):
      x = float(elem.attrib.get("left", 0))
      y = float(elem.attrib.get("top", 0))
      w = float(elem.attrib.get("width", 0))
      h = float(elem.attrib.get("height", 0))
      size = int(elem.attrib.get("charHeight", 12))
      fg = elem.attrib.get("foreColor", "#000000")
      conn = elem.find(".//connection")
      expr = conn.attrib.get("expression", "") if conn is not None else ""
      val = str(self.tag_overrides.get(expr, "0.0"))
      return (
          f'<text x="{x + w/2}" y="{y + h/2}" font-family="Arial, monospace"'
          f' font-size="{size}px" font-weight="bold" fill="{fg}"'
          f' text-anchor="middle" {tf} {tag_attr}>{val}</text>'
      )

    return ""

  def _flatten_and_render(self, node, accumulated_tags: list) -> list:
    rendered_elements = []
    if node.tag in (
        "displaySettings",
        "vbaProject",
        "animations",
        "connections",
        "transform",
    ):
      return rendered_elements
    current_tags = list(accumulated_tags)
    for lt in self._extract_local_tags(node):
      if lt not in current_tags:
        current_tags.append(lt)

    if node.tag == "group":
      for child in node:
        rendered_elements.extend(self._flatten_and_render(child, current_tags))
    else:
      svg_markup = self._render_primitive(node, current_tags)
      if svg_markup:
        rendered_elements.append(svg_markup)
    return rendered_elements

  def compile(self) -> str:
    all_primitives = []
    for child in self.root:
      all_primitives.extend(self._flatten_and_render(child, []))
    svg_content = "\n  ".join(all_primitives)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{ width: 100%; height: 100%; background: #121212; display: flex; flex-direction: column; overflow: hidden; font-family: Arial, sans-serif; }}
        #top-bar {{ height: 38px; background: #1f242d; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; color: #d1d5db; font-size: 13px; flex-shrink: 0; }}
        #toggle-btn {{ background: #2563eb; color: white; border: none; padding: 4px 12px; font-size: 12px; font-weight: bold; border-radius: 4px; cursor: pointer; }}
        .stage {{ flex: 1; width: 100%; height: calc(100vh - 38px); display: flex; justify-content: center; align-items: center; padding: 12px; overflow: hidden; }}
        svg {{ width: 100%; height: 100%; max-width: 100%; max-height: 100%; object-fit: contain; background-color: {self.bg_color}; box-shadow: 0 0 30px rgba(0, 0, 0, 0.9); }}
        text {{ user-select: none; dominant-baseline: central; }}
        .has-tag-info {{ cursor: pointer; }}
        .show-tags .has-tag-info {{ outline: 2px dashed #00e5ff !important; }}
        .has-tag-info:hover {{ outline: 2px solid #ffea00 !important; }}
        #tag-tooltip {{ position: fixed; bottom: 14px; left: 50%; transform: translateX(-50%); background: rgba(15, 23, 42, 0.95); color: #38bdf8; border: 1px solid #38bdf8; padding: 8px 16px; border-radius: 6px; font-family: monospace; font-size: 12px; display: none; z-index: 100; pointer-events: none; }}
        #inspector-modal {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0, 0, 0, 0.65); z-index: 200; justify-content: center; align-items: center; }}
        .modal-box {{ background: #1e293b; border: 1px solid #38bdf8; border-radius: 8px; width: 90%; max-width: 620px; display: flex; flex-direction: column; overflow: hidden; }}
        .modal-header {{ background: #0f172a; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; color: #e2e8f0; font-size: 13px; font-weight: bold; }}
        .modal-body {{ padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }}
        .modal-body textarea {{ width: 100%; height: 140px; background: #090d16; color: #38bdf8; border: 1px solid #334155; border-radius: 6px; padding: 10px; font-family: monospace; font-size: 13px; resize: vertical; outline: none; }}
        .modal-footer {{ display: flex; justify-content: space-between; align-items: center; }}
        .btn {{ padding: 6px 14px; border: none; border-radius: 4px; font-size: 12px; font-weight: bold; cursor: pointer; }}
        .btn-copy {{ background: #0284c7; color: white; }}
        .btn-close {{ background: #475569; color: white; }}
        #copy-status {{ color: #4ade80; font-size: 12px; display: none; }}
    </style>
</head>
<body>
    <div id="top-bar">
        <span><b>Screen:</b> {self.file_name} ({self.width}×{self.height})</span>
        <div><button id="toggle-btn" onclick="toggleTagOverlay()">Toggle Tag Highlight Box</button></div>
    </div>
    <div class="stage"><svg viewBox="0 0 {self.width} {self.height}" preserveAspectRatio="xMidYMid meet">{svg_content}</svg></div>
    <div id="tag-tooltip"></div>
    <div id="inspector-modal" onclick="closeInspectorModal()">
        <div class="modal-box" onclick="event.stopPropagation()">
            <div class="modal-header">
                <span>Element Tag & Expression Inspector</span>
                <button class="btn btn-close" onclick="closeInspectorModal()" style="padding: 2px 8px;">✕</button>
            </div>
            <div class="modal-body">
                <textarea id="modal-tag-textarea" spellcheck="false"></textarea>
                <div class="modal-footer">
                    <span id="copy-status">✓ Copied to clipboard!</span>
                    <div style="margin-left: auto; display: flex; gap: 8px;">
                        <button class="btn btn-copy" onclick="copyModalText()">Copy All</button>
                        <button class="btn btn-close" onclick="closeInspectorModal()">Close</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        const tooltip = document.getElementById('tag-tooltip');
        const modal = document.getElementById('inspector-modal');
        const modalTextarea = document.getElementById('modal-tag-textarea');
        const copyStatus = document.getElementById('copy-status');
        let overlayActive = false;
        let isModalOpen = false;

        function toggleTagOverlay() {{
            overlayActive = !overlayActive;
            document.body.classList.toggle('show-tags', overlayActive);
            document.getElementById('toggle-btn').textContent = overlayActive ? 'Hide Tag Outlines' : 'Toggle Tag Highlight Box';
        }}

        document.addEventListener('mouseover', (e) => {{
            if (isModalOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target) {{
                tooltip.style.display = 'block';
                tooltip.textContent = target.getAttribute('data-tag-info');
            }}
        }});

        document.addEventListener('mouseout', (e) => {{
            if (isModalOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target) tooltip.style.display = 'none';
        }});

        document.addEventListener('click', (e) => {{
            const target = e.target.closest('[data-tag-info]');
            if (target) {{
                e.stopPropagation();
                const rawInfo = target.getAttribute('data-tag-info');
                if (rawInfo) {{
                    modalTextarea.value = rawInfo.split(' | ').join('\\n');
                    modal.style.display = 'flex';
                    isModalOpen = true;
                    tooltip.style.display = 'none';
                    copyStatus.style.display = 'none';
                    setTimeout(() => {{ modalTextarea.focus(); modalTextarea.select(); }}, 50);
                }}
            }}
        }});

        function closeInspectorModal() {{
            modal.style.display = 'none';
            isModalOpen = false;
        }}

        function copyModalText() {{
            modalTextarea.select();
            navigator.clipboard.writeText(modalTextarea.value);
            copyStatus.style.display = 'inline';
            setTimeout(() => {{ copyStatus.style.display = 'none'; }}, 2000);
        }}

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape' && isModalOpen) closeInspectorModal();
        }});
    </script>
</body>
</html>"""


def select_file():
  root = tk.Tk()
  root.withdraw()
  root.attributes("-topmost", True)
  file_path = filedialog.askopenfilename(
      title="Select FactoryTalk View XML File",
      filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
  )
  root.destroy()
  return file_path


def main():
  xml_path = select_file()
  if not xml_path:
    sys.exit(0)

  file_name = os.path.basename(xml_path)
  with open(xml_path, "rb") as f:
    file_bytes = f.read()

  compiler = FlattenedFTViewCompiler(file_bytes, file_name)
  html_markup = compiler.compile()

  webview.create_window(
      title=f"FTView Screen Viewer - {file_name}",
      html=html_markup,
      width=1280,
      height=800,
      resizable=True,
  )
  webview.start()


if __name__ == "__main__":
  main()
