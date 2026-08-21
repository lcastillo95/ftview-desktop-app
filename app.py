import html
import io
import math
import os
import re
import sqlite3
import sys
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

    for k, v in elem.attrib.items():
      if isinstance(v, str):
        for tag_match in re.findall(r"\{(\/[A-Za-z0-9_]+/[^\}]+)\}", v):
          info.append(f"Tag: {tag_match}")

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

  def compile_svg_bundle(self) -> dict:
    all_primitives = []
    for child in self.root:
      all_primitives.extend(self._flatten_and_render(child, []))
    return {
        "svg": "\n  ".join(all_primitives),
        "width": self.width,
        "height": self.height,
        "bg_color": self.bg_color,
        "file_name": self.file_name,
    }


class FTViewDatabaseHub:

  def __init__(self):
    self.conn = sqlite3.connect(":memory:", check_same_thread=False)
    self.files_cache = {}
    self._init_db()

  def _init_db(self):
    cur = self.conn.cursor()
    cur.execute("""
            CREATE TABLE IF NOT EXISTS hmi_elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT,
                display_normalized TEXT,
                label_text TEXT,
                tags TEXT
            )
        """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_norm ON"
        " hmi_elements(display_normalized)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_disp ON hmi_elements(display_name)"
    )
    self.conn.commit()

  def normalize_display_name(self, name: str) -> str:
    base = os.path.splitext(name)[0]
    return re.sub(r"[^a-zA-Z0-9]", "", base).lower()

  def extract_ft_tags_from_text(self, text_val: str) -> list:
    if not text_val:
      return []
    bracketed = re.findall(r"\{(\/[A-Za-z0-9_]+/[^\}]+)\}", text_val)
    if bracketed:
      return bracketed
    if text_val.startswith("/") and "::" in text_val:
      return [text_val.strip("{}")]
    return []

  def parse_and_index_xml(self, file_path: str):
    display_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
      xml_bytes = f.read()

    self.files_cache[display_name] = xml_bytes
    norm_name = self.normalize_display_name(display_name)

    tree = ET.parse(io.BytesIO(xml_bytes))
    root = tree.getroot()

    cur = self.conn.cursor()
    cur.execute(
        "DELETE FROM hmi_elements WHERE display_name = ?", (display_name,)
    )

    rows_to_insert = []
    for elem in root.iter():
      texts = []
      cap = elem.attrib.get("caption")
      if cap:
        clean = (
            cap.replace("&#xA;", "\n")
            .replace("\r\n", "\n")
            .strip()
        )
        if clean:
          texts.append(clean)

      for sub_cap in elem.findall(".//caption"):
        sc = sub_cap.attrib.get("caption", "").strip()
        if sc and sc not in texts:
          texts.append(sc)

      tags = []
      for attr_name, attr_val in elem.attrib.items():
        if isinstance(attr_val, str):
          for t in self.extract_ft_tags_from_text(attr_val):
            if t not in tags:
              tags.append(t)

      for conn in elem.findall("./connections/connection"):
        expr = conn.attrib.get("expression")
        if expr:
          extracted = self.extract_ft_tags_from_text(expr)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif expr not in tags:
            tags.append(expr)

      for anim in elem.findall("./animations/*"):
        expr = anim.attrib.get("expression")
        if expr:
          extracted = self.extract_ft_tags_from_text(expr)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif expr not in tags:
            tags.append(expr)

      for act in elem.findall("./action"):
        t = act.attrib.get("tag")
        if t:
          extracted = self.extract_ft_tags_from_text(t)
          if extracted:
            tags.extend([x for x in extracted if x not in tags])
          elif t not in tags:
            tags.append(t)

      for cmd in elem.findall("./command"):
        for attr in ("pressAction", "releaseAction"):
          c = cmd.attrib.get(attr)
          if c:
            extracted = self.extract_ft_tags_from_text(c)
            if extracted:
              tags.extend([x for x in extracted if x not in tags])
            elif c not in tags:
              tags.append(c)

      if texts or tags:
        label_text_col = "\n".join(texts)
        tags_col = " | ".join(tags)
        rows_to_insert.append(
            (display_name, norm_name, label_text_col, tags_col)
        )

    if rows_to_insert:
      cur.executemany(
          """
                INSERT INTO hmi_elements (display_name, display_normalized, label_text, tags)
                VALUES (?, ?, ?, ?)
            """,
          rows_to_insert,
      )

    self.conn.commit()

  def get_summary(self):
    cur = self.conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT display_name), COUNT(*) FROM hmi_elements"
    )
    displays_count, elements_count = cur.fetchone()
    return {"displays": displays_count or 0, "elements": elements_count or 0}

  def search_by_display(self, query: str):
    norm_q = self.normalize_display_name(query)
    cur = self.conn.cursor()
    if not norm_q:
      cur.execute(
          "SELECT DISTINCT display_name, display_normalized FROM hmi_elements"
          " ORDER BY display_name"
      )
    else:
      cur.execute(
          """
                SELECT DISTINCT display_name, display_normalized FROM hmi_elements 
                WHERE display_normalized LIKE ? OR display_name LIKE ?
                ORDER BY display_name
            """,
          (f"%{norm_q}%", f"%{query}%"),
      )

    rows = cur.fetchall()
    return [
        {"display_name": r[0], "display_normalized": r[1]} for r in rows
    ]

  def search_by_label(self, query: str):
    if not query.strip():
      return []
    cur = self.conn.cursor()
    cur.execute(
        """
            SELECT display_name, label_text, tags 
            FROM hmi_elements 
            WHERE label_text LIKE ? 
            ORDER BY display_name
        """,
        (f"%{query}%",),
    )
    rows = cur.fetchall()
    return [{"display_name": r[0], "label_text": r[1], "tags": r[2]} for r in rows]

  def search_by_tag(self, query: str):
    if not query.strip():
      return []
    cur = self.conn.cursor()
    cur.execute(
        """
            SELECT display_name, label_text, tags 
            FROM hmi_elements 
            WHERE tags LIKE ? 
            ORDER BY display_name
        """,
        (f"%{query}%",),
    )
    rows = cur.fetchall()
    return [{"display_name": r[0], "label_text": r[1], "tags": r[2]} for r in rows]


class DesktopAppBridge:

  def __init__(self, db: FTViewDatabaseHub):
    self.db = db
    self.window = None

  def open_file_picker(self):
    if not self.window:
      return []
    # Native Webview File Dialog - runs smoothly without Tkinter freeze
    file_types = (
        "FactoryTalk XML Files (*.xml)",
        "All files (*.*)",
    )
    result = self.window.create_file_dialog(
        webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types
    )
    return list(result) if result else []

  def parse_single_file(self, file_path: str):
    self.db.parse_and_index_xml(file_path)
    return self.db.get_summary()

  def get_current_stats(self):
    return self.db.get_summary()

  def search_displays(self, query):
    return self.db.search_by_display(query)

  def search_labels(self, query):
    return self.db.search_by_label(query)

  def search_tags(self, query):
    return self.db.search_by_tag(query)

  def get_screen_render_data(self, display_name):
    xml_bytes = self.db.files_cache.get(display_name)
    if not xml_bytes:
      return None
    compiler = FlattenedFTViewCompiler(xml_bytes, display_name)
    return compiler.compile_svg_bundle()


MAIN_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>FactoryTalk View SE Analyzer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }
        header {
            background-color: #1e293b;
            border-bottom: 1px solid #334155;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10;
        }
        .header-title { display: flex; flex-direction: column; }
        .header-title h1 { font-size: 18px; font-weight: 700; color: #38bdf8; letter-spacing: -0.5px; }
        .header-title .author-badge { font-size: 12px; color: #94a3b8; margin-top: 2px; }
        .header-title .author-badge b { color: #f59e0b; }
        .btn {
            background-color: #0284c7;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn:hover { background-color: #0369a1; }
        .btn-success { background-color: #10b981; }
        .btn-success:hover { background-color: #059669; }
        .btn-nav { background: #334155; color: #f1f5f9; }
        .btn-nav:hover { background: #475569; }

        .container { display: flex; flex: 1; overflow: hidden; position: relative; }
        
        .sidebar {
            width: 220px;
            background: #182234;
            border-right: 1px solid #334155;
            display: flex;
            flex-direction: column;
            padding: 16px 10px;
            gap: 6px;
        }
        .nav-item {
            display: flex;
            align-items: center;
            padding: 10px 14px;
            border-radius: 6px;
            color: #cbd5e1;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .nav-item:hover { background-color: #243248; color: #ffffff; }
        .nav-item.active { background-color: #0284c7; color: #ffffff; font-weight: 600; }

        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 24px;
            overflow-y: auto;
        }
        .stats-bar { display: flex; gap: 16px; margin-bottom: 20px; }
        .stat-card {
            background: #1e293b;
            border: 1px solid #334155;
            padding: 12px 18px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            min-width: 160px;
        }
        .stat-label { font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 600; }
        .stat-value { font-size: 20px; font-weight: 700; color: #38bdf8; }

        .search-box-wrapper { margin-bottom: 16px; }
        .search-input {
            width: 100%;
            padding: 12px 16px;
            background: #1e293b;
            border: 1px solid #475569;
            border-radius: 8px;
            color: #f8fafc;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        .search-input:focus { border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2); }

        .results-container {
            flex: 1;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            overflow: auto;
        }
        table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
        th {
            background-color: #0f172a;
            color: #94a3b8;
            padding: 12px 16px;
            font-weight: 600;
            border-bottom: 1px solid #334155;
            position: sticky;
            top: 0;
            z-index: 2;
        }
        td { padding: 12px 16px; border-bottom: 1px solid #293548; color: #e2e8f0; vertical-align: top; }
        tr:hover td { background-color: #243248; }
        .screen-link { color: #38bdf8; font-weight: 600; cursor: pointer; text-decoration: underline; }
        .screen-link:hover { color: #7dd3fc; }
        .tag-pill {
            display: inline-block;
            background: #090d16;
            color: #38bdf8;
            font-family: monospace;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #334155;
            margin: 2px 0;
            word-break: break-all;
        }
        .text-preview { white-space: pre-line; color: #cbd5e1; }
        .empty-state { padding: 40px; text-align: center; color: #64748b; font-size: 14px; }

        /* Progress Bar Modal */
        #progress-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.75);
            z-index: 500;
            justify-content: center;
            align-items: center;
        }
        .progress-box {
            background: #1e293b;
            border: 1px solid #38bdf8;
            border-radius: 8px;
            padding: 24px;
            width: 450px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.8);
        }
        .progress-track {
            width: 100%;
            height: 12px;
            background: #0f172a;
            border-radius: 6px;
            overflow: hidden;
            border: 1px solid #334155;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #0284c7, #38bdf8);
            transition: width 0.1s ease;
        }

        /* Screen Viewer Fullscreen Stage Overlay */
        #screen-viewer-view {
            display: none;
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: #121212;
            z-index: 100;
            flex-direction: column;
        }
        .viewer-top-bar {
            height: 42px;
            background: #1f242d;
            border-bottom: 1px solid #334155;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 16px;
            color: #d1d5db;
            font-size: 13px;
        }
        .viewer-stage {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 12px;
            overflow: hidden;
        }
        #screen-svg-canvas {
            width: 100%;
            height: 100%;
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            box-shadow: 0 0 30px rgba(0,0,0,0.9);
        }
        .has-tag-info { cursor: pointer; }
        .show-tags .has-tag-info { outline: 2px dashed #00e5ff !important; }
        .has-tag-info:hover { outline: 2px solid #ffea00 !important; }
        #viewer-tag-tooltip {
            position: fixed;
            bottom: 14px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.95);
            color: #38bdf8;
            border: 1px solid #38bdf8;
            padding: 8px 16px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 12px;
            display: none;
            z-index: 150;
            pointer-events: none;
        }
        #inspector-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0, 0, 0, 0.65);
            z-index: 300;
            justify-content: center;
            align-items: center;
        }
        .modal-box {
            background: #1e293b;
            border: 1px solid #38bdf8;
            border-radius: 8px;
            width: 90%;
            max-width: 620px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .modal-header {
            background: #0f172a;
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            color: #e2e8f0;
            font-size: 13px;
            font-weight: bold;
        }
        .modal-body { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
        .modal-body textarea {
            width: 100%;
            height: 140px;
            background: #090d16;
            color: #38bdf8;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px;
            font-family: monospace;
            font-size: 13px;
            resize: vertical;
            outline: none;
        }
        .modal-footer { display: flex; justify-content: space-between; align-items: center; }
    </style>
</head>
<body>

    <header>
        <div class="header-title">
            <h1>FactoryTalk View SE HMI Analyzer</h1>
            <div class="author-badge">Created by <b>Luis Castillo</b></div>
        </div>
        <div>
            <button class="btn btn-success" onclick="loadFilesBatch()">+ Load & Parse XML Files</button>
        </div>
    </header>

    <div class="container">
        <div class="sidebar">
            <div class="nav-item active" id="tab-displays" onclick="switchTab('displays')">Display Names</div>
            <div class="nav-item" id="tab-labels" onclick="switchTab('labels')">Label & Text Search</div>
            <div class="nav-item" id="tab-tags" onclick="switchTab('tags')">PLC Tag Cross-Ref</div>
        </div>

        <div class="main-content">
            <div class="stats-bar">
                <div class="stat-card">
                    <span class="stat-label">Loaded Displays</span>
                    <span class="stat-value" id="stat-displays">0</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Indexed Elements</span>
                    <span class="stat-value" id="stat-elements">0</span>
                </div>
            </div>

            <div class="search-box-wrapper">
                <input type="text" id="main-search-input" class="search-input" 
                       placeholder="Search displays (ignores dashes, underscores, and spacing)..." 
                       oninput="onSearchInput(this.value)">
            </div>

            <div class="results-container">
                <table id="results-table">
                    <thead id="table-head"></thead>
                    <tbody id="table-body">
                        <tr><td colspan="4" class="empty-state">No XML files loaded. Click "+ Load & Parse XML Files" to begin.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Dedicated SVG Viewer Overlay Stage -->
        <div id="screen-viewer-view">
            <div class="viewer-top-bar">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <button class="btn btn-nav" onclick="closeScreenViewer()">← Back to Search Hub</button>
                    <span id="viewer-screen-title"><b>Screen:</b></span>
                </div>
                <div>
                    <button id="toggle-tag-btn" class="btn" onclick="toggleTagOverlay()">Toggle Tag Highlight Box</button>
                </div>
            </div>
            <div class="viewer-stage">
                <svg id="screen-svg-canvas" preserveAspectRatio="xMidYMid meet"></svg>
            </div>
        </div>
    </div>

    <!-- Progress Modal -->
    <div id="progress-modal">
        <div class="progress-box">
            <h3 style="font-size: 15px; color: #38bdf8;">Parsing & Indexing XML Files...</h3>
            <div class="progress-track">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8;">
                <span id="progress-status-file">Processing...</span>
                <span id="progress-status-count">0 / 0</span>
            </div>
        </div>
    </div>

    <!-- Inspector Modal -->
    <div id="viewer-tag-tooltip"></div>
    <div id="inspector-modal" onclick="closeInspectorModal()">
        <div class="modal-box" onclick="event.stopPropagation()">
            <div class="modal-header">
                <span>Element Tag & Expression Inspector</span>
                <button class="btn btn-nav" onclick="closeInspectorModal()" style="padding: 2px 8px;">✕</button>
            </div>
            <div class="modal-body">
                <textarea id="modal-tag-textarea" spellcheck="false"></textarea>
                <div class="modal-footer">
                    <span id="copy-status" style="color: #4ade80; font-size: 12px; display: none;">✓ Copied to clipboard!</span>
                    <div style="margin-left: auto; display: flex; gap: 8px;">
                        <button class="btn" style="background:#0284c7;" onclick="copyModalText()">Copy All</button>
                        <button class="btn btn-nav" onclick="closeInspectorModal()">Close</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTab = 'displays';
        let overlayActive = false;
        let isInspectorOpen = false;

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');

            const searchInput = document.getElementById('main-search-input');
            if (tab === 'displays') {
                searchInput.placeholder = "Search displays (ignores dashes, underscores, and spaces)...";
            } else if (tab === 'labels') {
                searchInput.placeholder = "Type text to find all screens where this caption appears...";
            } else if (tab === 'tags') {
                searchInput.placeholder = "Search by PLC tag e.g. /CH01/Data_1::[CH01_042] or Status...";
            }
            onSearchInput(searchInput.value);
        }

        async function loadFilesBatch() {
            const fileList = await window.pywebview.api.open_file_picker();
            if (!fileList || fileList.length === 0) return;

            const modal = document.getElementById('progress-modal');
            const fill = document.getElementById('progress-fill');
            const fileStatus = document.getElementById('progress-status-file');
            const countStatus = document.getElementById('progress-status-count');

            modal.style.display = 'flex';
            const total = fileList.length;
            let summary = null;

            for (let i = 0; i < total; i++) {
                const path = fileList[i];
                const fileName = path.replace(/^.*[\\\\/]/, '');
                fileStatus.textContent = fileName;
                countStatus.textContent = `${i + 1} / ${total}`;
                fill.style.width = `${Math.round(((i + 1) / total) * 100)}%`;

                summary = await window.pywebview.api.parse_single_file(path);
            }

            modal.style.display = 'none';
            if (summary) {
                document.getElementById('stat-displays').textContent = summary.displays;
                document.getElementById('stat-elements').textContent = summary.elements;
                onSearchInput(document.getElementById('main-search-input').value);
            }
        }

        async function onSearchInput(query) {
            const tbody = document.getElementById('table-body');
            const thead = document.getElementById('table-head');

            if (currentTab === 'displays') {
                thead.innerHTML = `<tr><th>Display Name</th><th>Normalized Identifier</th><th>Action</th></tr>`;
                const results = await window.pywebview.api.search_displays(query);
                if (results.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No matching displays found.</td></tr>`;
                    return;
                }
                tbody.innerHTML = results.map(r => `
                    <tr>
                        <td><b>${r.display_name}</b></td>
                        <td style="font-family: monospace; color: #94a3b8;">${r.display_normalized}</td>
                        <td><span class="screen-link" onclick="openScreen('${r.display_name}')">Launch Screen View →</span></td>
                    </tr>
                `).join('');

            } else if (currentTab === 'labels') {
                thead.innerHTML = `<tr><th>Display</th><th>Label / Caption Found</th><th>Associated Tag(s)</th></tr>`;
                if (!query.trim()) {
                    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Type text above to search screen labels.</td></tr>`;
                    return;
                }
                const results = await window.pywebview.api.search_labels(query);
                if (results.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No screens found containing "${query}".</td></tr>`;
                    return;
                }
                tbody.innerHTML = results.map(r => `
                    <tr>
                        <td><span class="screen-link" onclick="openScreen('${r.display_name}')">${r.display_name}</span></td>
                        <td class="text-preview">${escapeHtml(r.label_text)}</td>
                        <td>${formatTags(r.tags)}</td>
                    </tr>
                `).join('');

            } else if (currentTab === 'tags') {
                thead.innerHTML = `<tr><th>Display</th><th>PLC Tag / Expression</th><th>Associated Text</th></tr>`;
                if (!query.trim()) {
                    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Type a tag pattern above to cross-reference displays.</td></tr>`;
                    return;
                }
                const results = await window.pywebview.api.search_tags(query);
                if (results.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No screens found referencing "${query}".</td></tr>`;
                    return;
                }
                tbody.innerHTML = results.map(r => `
                    <tr>
                        <td><span class="screen-link" onclick="openScreen('${r.display_name}')">${r.display_name}</span></td>
                        <td>${formatTags(r.tags)}</td>
                        <td class="text-preview">${escapeHtml(r.label_text || '-')}</td>
                    </tr>
                `).join('');
            }
        }

        async function openScreen(displayName) {
            const data = await window.pywebview.api.get_screen_render_data(displayName);
            if (!data) return;

            const svg = document.getElementById('screen-svg-canvas');
            svg.setAttribute('viewBox', `0 0 ${data.width} ${data.height}`);
            svg.style.backgroundColor = data.bg_color;
            svg.innerHTML = data.svg;

            document.getElementById('viewer-screen-title').innerHTML = `<b>Screen:</b> ${data.file_name} (${data.width}×${data.height})`;
            document.getElementById('screen-viewer-view').style.display = 'flex';
        }

        function closeScreenViewer() {
            document.getElementById('screen-viewer-view').style.display = 'none';
        }

        function toggleTagOverlay() {
            overlayActive = !overlayActive;
            document.getElementById('screen-viewer-view').classList.toggle('show-tags', overlayActive);
            document.getElementById('toggle-tag-btn').textContent = overlayActive ? 'Hide Tag Outlines' : 'Toggle Tag Highlight Box';
        }

        const tooltip = document.getElementById('viewer-tag-tooltip');
        const inspectorModal = document.getElementById('inspector-modal');
        const modalTextarea = document.getElementById('modal-tag-textarea');
        const copyStatus = document.getElementById('copy-status');

        document.addEventListener('mouseover', (e) => {
            if (isInspectorOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target && document.getElementById('screen-viewer-view').style.display === 'flex') {
                tooltip.style.display = 'block';
                tooltip.textContent = target.getAttribute('data-tag-info');
            }
        });

        document.addEventListener('mouseout', (e) => {
            if (isInspectorOpen) return;
            const target = e.target.closest('[data-tag-info]');
            if (target) tooltip.style.display = 'none';
        });

        document.addEventListener('click', (e) => {
            const target = e.target.closest('[data-tag-info]');
            if (target && document.getElementById('screen-viewer-view').style.display === 'flex') {
                e.stopPropagation();
                const rawInfo = target.getAttribute('data-tag-info');
                if (rawInfo) {
                    modalTextarea.value = rawInfo.split(' | ').join('\\n');
                    inspectorModal.style.display = 'flex';
                    isInspectorOpen = true;
                    tooltip.style.display = 'none';
                    copyStatus.style.display = 'none';
                    setTimeout(() => { modalTextarea.focus(); modalTextarea.select(); }, 50);
                }
            }
        });

        function closeInspectorModal() {
            inspectorModal.style.display = 'none';
            isInspectorOpen = false;
        }

        function copyModalText() {
            modalTextarea.select();
            navigator.clipboard.writeText(modalTextarea.value);
            copyStatus.style.display = 'inline';
            setTimeout(() => { copyStatus.style.display = 'none'; }, 2000);
        }

        function formatTags(tagString) {
            if (!tagString) return '<span style="color:#64748b;">None</span>';
            return tagString.split(' | ').map(t => `<div class="tag-pill">${escapeHtml(t)}</div>`).join('');
        }

        function escapeHtml(text) {
            return (text || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (isInspectorOpen) closeInspectorModal();
                else if (document.getElementById('screen-viewer-view').style.display === 'flex') closeScreenViewer();
            }
        });
    </script>
</body>
</html>"""


def main():
  db = FTViewDatabaseHub()
  bridge = DesktopAppBridge(db)

  window = webview.create_window(
      title="FactoryTalk View SE HMI Analyzer - Created by Luis Castillo",
      html=MAIN_PORTAL_HTML,
      js_api=bridge,
      width=1360,
      height=860,
      resizable=True,
  )
  bridge.window = window
  webview.start()


if __name__ == "__main__":
  main()
